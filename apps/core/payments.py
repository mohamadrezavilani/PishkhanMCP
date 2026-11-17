"""Payment orchestration using the supplied Core contracts.

Browser return URLs are not webhooks. Core verifies IPG/CNPG and processes its
provider webhooks; MCP reconciles their authoritative state with PaymentInfo.
"""

import hashlib
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.errors import PishkhanError
from apps.core.models import Operation, PaymentAttempt, ProviderCall, Quote
from apps.core.payment_progress import payment_progress
from apps.core.tracing import current_request, ensure_request
from apps.providers.registry import find_action


def gateway_flow(gateway):
    name = gateway.casefold()
    if name.startswith("inapp_cnpg_"):
        return "inapp_cnpg"
    if name.startswith("cnpg_"):
        return "cnpg"
    if name.startswith(("wallet_ewano", "wallet_app", "wallet_sadad")):
        return "external_wallet"
    if name.startswith("wallet"):
        return "wallet"
    return "ipg"


def gateway_names(channels):
    names = set()
    for channel in channels if isinstance(channels, list) else []:
        if not isinstance(channel, dict) or channel.get("Active") is False:
            continue
        for gateway in channel.get("Gateways") or []:
            if isinstance(gateway, dict) and gateway.get("Active") is not False:
                kind = gateway.get("Type") or {}
                if isinstance(kind, dict) and isinstance(kind.get("Name"), str):
                    names.add(kind["Name"])
    return names


def require_gateway(gateway, channels):
    names = gateway_names(channels)
    if gateway not in names:
        raise PishkhanError(
            "INVALID_GATEWAY",
            "\u062f\u0631\u06af\u0627\u0647 \u0631\u0627 \u0627\u0632 \u06af\u0632\u06cc\u0646\u0647\u200c\u0647\u0627\u06cc \u0641\u0639\u0627\u0644 \u0647\u0645\u06cc\u0646 \u0635\u0648\u0631\u062a\u062d\u0633\u0627\u0628 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.",
            details={"gateways": sorted(names)},
        )


def _attempt(session, payment_key):
    try:
        return PaymentAttempt.objects.get(session=session, payment_key=payment_key)
    except PaymentAttempt.DoesNotExist as exc:
        raise PishkhanError("PAYMENT_NOT_FOUND", "PaymentKey has not been created in this session.") from exc


def payment_status(session_id, payment_key):
    from apps.core import operations as ops

    session = ops.get_session(session_id)
    attempt = _attempt(session, payment_key)
    if session.mode != "live":
        return {"demo": True, **attempt.public_dict()}
    response = ops.live_call(session, find_action("PaymentInfo", "core"), {"PaymentKey": payment_key})
    attempt.refresh_from_db()
    status = attempt.status
    progress = payment_progress(attempt)
    # This enables result retrieval, not a claim that the service was delivered.
    if attempt.purchase_key and status in {"Paid", "Settle"}:
        for quote in Quote.objects.filter(session=session, parameters__purchase_key=attempt.purchase_key):
            quote.parameters["payment_completed"] = True
            if quote.parameters.get("stage") == "payment_pending":
                ops._set_stage(quote)
            quote.save(update_fields=["parameters"])
    targets = Operation.objects.filter(
        session=session, request_data__PaymentKey=payment_key, action_id__startswith="CnpgPayment:"
    )
    origin = [attempt.operation] if attempt.operation_id else []
    for operation in [*origin, *targets]:
        operation.status = (
            Operation.Status.COMPLETED
            if progress["payment_complete"]
            else Operation.Status.FAILED
            if status in {"Return", "Unpayable"}
            else Operation.Status.REQUIRES_ACTION
            if status == "Unpaid"
            else Operation.Status.PENDING
            if status in {"Paid", "Settle", "InProcess"}
            else Operation.Status.UNKNOWN
        )
        operation.result = {
            **operation.result,
            **progress,
            "payment_key": payment_key,
        }
        if progress["payment_complete"]:
            operation.result["next_step"] = "none"
        operation.save(update_fields=["status", "result", "updated_at"])
    data = response.get("parameters", {})
    return {
        **attempt.public_dict(),
        **progress,
        "transaction_details": data.get("ExtraInfo") if isinstance(data, dict) else None,
        "amount": data.get("Amount") if isinstance(data, dict) else None,
        "fee": data.get("Fee") if isinstance(data, dict) else None,
        "total_amount": data.get("TotalAmount") if isinstance(data, dict) else None,
        "currency": "IRR",
        "authority": "core.svc/v1/PaymentInfo",
        "notice": "payment_complete ends the verified payment task, not carrier reconciliation. "
        "settled reflects only the raw payment Settle state; inspect all bill states separately. "
        "Paid does not guarantee a later Settle transition. Do not pay again to check status.",
    }


def _finish_start(session, result, gateway):
    from apps.core import operations as ops

    data = result.get("parameters")
    if not isinstance(data, dict) or not isinstance(data.get("PaymentKey"), str):
        raise PishkhanError(
            "PAYMENT_KEY_MISSING", "Payment response has no PaymentKey.", details={"outcome": "unknown"}
        )
    key = data["PaymentKey"]
    flow = gateway_flow(gateway)
    payload = {
        **result,
        "payment_key": key,
        "payment_flow": flow,
        "financial_state": "unknown",
        "callback_mode": "custom" if (settings.P24_PAYMENT_CALLBACK or "").strip() else "core_default",
    }
    if flow == "wallet":
        ops.live_call(session, find_action("WalletPayment", "core"), {"PaymentKey": key})
        try:
            payload["payment_state"] = payment_status(str(session.pk), key)
            payload["financial_state"] = payload["payment_state"]["financial_state"]
        except PishkhanError as exc:
            payload["status_error"] = exc.as_dict()["error"]
        payload["pending"] = payload.get("payment_state", {}).get("pending", True)
    else:
        payload["requires_user_action"] = True
    payload["next_step"] = (
        "p24_cnpg_request_otp then p24_cnpg_payment with session-key encrypted EncryptData"
        if flow == "cnpg"
        else "Complete the provider's native/external flow, then p24_payment_status"
        if flow in {"inapp_cnpg", "external_wallet"}
        else "Complete RedirectLink if present, then p24_payment_status"
    )
    return payload


def pay_quote(session_id, quote_id, gateway, use_credit, idempotency_key):
    from apps.core import operations as ops

    session = ops.get_session(session_id)
    quote = ops.get_quote(session, quote_id)
    if session.mode == "demo":
        return {"demo": True, "quote_id": str(quote.pk), "next_step": "p24_run_inquiry"}
    if quote.parameters.get("stage") not in {"payment_required", "payment_pending", "ready"}:
        return ops.quote_dict(quote)
    if quote.parameters.get("payment_completed") or not quote.parameters.get("purchase_key"):
        return ops.quote_dict(quote)
    channels = ops._invoice_parameters(quote).get("PaymentChannels", [])
    if not channels:
        return ops.quote_dict(quote)
    require_gateway(gateway, channels)
    wire = {
        "Callback": (settings.P24_PAYMENT_CALLBACK or "").strip(),
        "Gateway": gateway,
        "PurchaseKey": quote.parameters["purchase_key"],
        "UseCredit": use_credit,
    }

    def perform():
        result = ops.live_call(session, find_action("InvoicePayment", "core"), wire)
        data = result.get("parameters")
        if not isinstance(data, dict):
            raise PishkhanError(
                "PAYMENT_FORMAT", "Payment response is not an object.", details={"outcome": "unknown"}
            )
        quote.parameters.update(payment_started=True, payment=data, stage="payment_pending")
        quote.save(update_fields=["parameters"])
        payload = _finish_start(session, result, gateway)
        quote.refresh_from_db()
        return {**payload, "quote": ops.quote_dict(quote)}

    return ops.execute_once(
        session,
        "pay_quote",
        wire,
        f"payment:{quote.pk}",
        perform,
        service_id=quote.service_id,
        request=quote.request,
    )


def _resume_callback_preflight(session, key, parameters, executor):
    """Reclaim a proven pre-payment validation failure with a conditional UPDATE.

    CALLBACK_NOT_CONFIGURED still requires identical inputs and zero calls.
    INVALID_GATEWAY may change only Gateway, and only when every recorded call
    is a successful BillsPaymentChannels read. Never reclaim an uncertain charge.
    """
    from apps.core import operations as ops

    operation = (
        Operation.objects.select_related("session", "request")
        .filter(session=session, idempotency_key=key, action_id="bill_payment")
        .first()
    )
    if not operation or operation.status != Operation.Status.FAILED:
        return None
    error = operation.result.get("error", {}) if isinstance(operation.result, dict) else {}
    reason = error.get("code") if isinstance(error, dict) else None
    if reason not in {"CALLBACK_NOT_CONFIGURED", "INVALID_GATEWAY"}:
        return None
    old_parameters = operation.request_data
    old_raw = json.dumps(
        {"action": "bill_payment", "parameters": old_parameters}, sort_keys=True, ensure_ascii=False
    )
    if operation.request_hash != hashlib.sha256(old_raw.encode()).hexdigest():
        return None
    if reason == "CALLBACK_NOT_CONFIGURED":
        if old_parameters != parameters:
            return None
        disallowed_calls = ProviderCall.objects.filter(operation_id=operation.pk)
    else:
        if {k: v for k, v in old_parameters.items() if k != "Gateway"} != {
            k: v for k, v in parameters.items() if k != "Gateway"
        }:
            return None
        allowed = ProviderCall.objects.filter(
            operation_id=operation.pk,
            action_id="core_bills_payment_channels_v1",
            status="succeeded",
            upstream_code="G00000",
        )
        if not allowed.exists():
            return None
        disallowed_calls = ProviderCall.objects.filter(operation_id=operation.pk).exclude(
            pk__in=allowed.values("pk")
        )
    raw = json.dumps({"action": "bill_payment", "parameters": parameters}, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
    if current_request() and operation.request_id and operation.request_id != current_request().pk:
        raise PishkhanError("REQUEST_MISMATCH", "This idempotency key belongs to another request.")

    # Keep every guard in the write predicate; checking first and then updating
    # unconditionally would let two concurrent callers repeat the payment.
    eligible = (
        Operation.objects.filter(
            pk=operation.pk,
            status=Operation.Status.FAILED,
            result=operation.result,
            request_id=operation.request_id,
            request_hash=operation.request_hash,
            request_data=old_parameters,
            upstream_reference="",
        )
        .exclude(pk__in=disallowed_calls.values("operation_id"))
        .exclude(pk__in=PaymentAttempt.objects.filter(operation_id=operation.pk).values("operation_id"))
    )
    claimed = eligible.update(
        status=Operation.Status.RUNNING,
        request_hash=fingerprint,
        request_data=parameters,
        updated_at=timezone.now(),
    )
    operation.refresh_from_db()
    if not claimed:
        return ops._operation_response(operation, replayed=True)

    def resumed():
        result = executor()
        result["preflight_recovery"] = {"reason": reason, "previous_gateway": old_parameters.get("Gateway")}
        return result

    return ops._complete_operation(operation, resumed)


def prepare_bill_payment(session_id, bill_ids, gateway, idempotency_key, service_name=None):
    from apps.core import operations as ops

    session = ops.get_session(session_id)
    bill_ids = sorted(set(bill_ids))
    request = current_request()
    service_id = request.service_id if request else ""
    if session.mode == "live" and not service_name:
        names = {"electricity": "v1_InquiryElectricBills", "water": "v1_InquiryWaterBills"}
        service_name = names.get(service_id)
        if not service_name:
            raise PishkhanError(
                "SERVICE_NAME_REQUIRED",
                "Use the Service name of this bill inquiry; it is not always electricity.",
            )

    def perform():
        if session.mode == "demo":
            return {
                "demo": True,
                "bill_ids": bill_ids,
                "requires_user_action": True,
                "notice": "No money moved.",
                "next_step": "p24_demo_complete_payment",
            }
        channels = ops.live_call(
            session, find_action("BillsPaymentChannels", "core"), {"Service": service_name, "Bills": bill_ids}
        )
        require_gateway(gateway, channels.get("parameters", {}).get("PaymentChannels", []))
        response = ops.live_call(
            session,
            find_action("BillsPayment", "core"),
            {
                "Callback": (settings.P24_PAYMENT_CALLBACK or "").strip(),
                "Gateway": gateway,
                "Bills": bill_ids,
            },
        )
        return _finish_start(session, response, gateway)

    wire = {"Bills": bill_ids, "Gateway": gateway, "Service": service_name}
    # Stable subject reservation: another model-generated key must not make a second payment.
    key = (
        "bills:" + hashlib.sha256(json.dumps(bill_ids).encode()).hexdigest()
        if session.mode == "live"
        else idempotency_key
    )
    if session.mode == "live":
        recovered = _resume_callback_preflight(session, key, wire, perform)
        if recovered is not None:
            return recovered
    return ops.execute_once(session, "bill_payment", wire, key, perform, service_id=service_id)


def cnpg(session_id, payment_key, encrypted_data, idempotency_key, *, pay=False):
    from apps.core import operations as ops

    session = ops.get_session(session_id)
    if session.mode != "live":
        raise PishkhanError("LIVE_ACTION_ONLY", "CNPG is not simulated; use the demo bill workflow.")
    attempt = _attempt(session, payment_key)
    if gateway_flow(attempt.gateway) != "cnpg":
        raise PishkhanError("CNPG_GATEWAY_REQUIRED", "This PaymentKey does not use a CNPG_ gateway.")
    action = "CnpgPayment" if pay else "CnpgRequestOtp"
    operation_name = action + ":" + hashlib.sha256(payment_key.encode()).hexdigest()
    if pay:
        latest = Operation.objects.filter(session=session, action_id=operation_name).first()
        if latest and latest.status != Operation.Status.FAILED:
            return ops._operation_response(latest, replayed=True)
    wire = {"PaymentKey": payment_key, "EncryptData": encrypted_data}

    def perform():
        response = ops.live_call(session, find_action(action, "core"), wire)
        if not pay:
            return {
                **response,
                "payment_key": payment_key,
                "requires_user_action": True,
                "next_step": "p24_cnpg_payment with new encrypted payload containing the entered payment OTP",
            }
        try:
            state = payment_status(session_id, payment_key)
            return {
                **response,
                "payment_key": payment_key,
                "payment_state": state,
                "pending": state["pending"],
            }
        except PishkhanError as exc:
            return {
                **response,
                "payment_key": payment_key,
                "pending": True,
                "status_error": exc.as_dict()["error"],
                "next_step": "p24_payment_status; do not pay again",
            }

    if not pay:
        return ops.execute_once(
            session, operation_name, wire, idempotency_key, perform, request=attempt.request
        )
    fingerprint = hashlib.sha256(
        json.dumps({"action": operation_name, "parameters": wire}, sort_keys=True).encode()
    ).hexdigest()
    # Reserve before any money-moving call; serialize by PaymentKey on PostgreSQL.
    with transaction.atomic():
        locked = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        latest = Operation.objects.filter(session=session, action_id=operation_name).first()
        if latest and latest.status != Operation.Status.FAILED:
            return ops._operation_response(latest, replayed=True)
        key = "cnpg:" + hashlib.sha256((payment_key + ":" + idempotency_key).encode()).hexdigest()
        op, created = Operation.objects.get_or_create(
            session=session,
            idempotency_key=key,
            defaults={
                "request": locked.request or ensure_request(session, key),
                "action_id": operation_name,
                "request_hash": fingerprint,
                "request_data": {"PaymentKey": payment_key, "EncryptData": "[redacted]"},
            },
        )
        if not created:
            if op.request_hash != fingerprint:
                raise PishkhanError(
                    "IDEMPOTENCY_CONFLICT", "CNPG key was already used for a different payload."
                )
            return ops._operation_response(op, replayed=True)
    return ops._complete_operation(op, perform)
