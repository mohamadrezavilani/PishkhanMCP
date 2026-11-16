"""Session identity, user behavior, transport attempts and explicit correlations.

MCP request_id is local. The supplied HAR does not expose the Core RequestID;
we never manufacture it or send an undocumented header to impersonate it.
"""

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.errors import PishkhanError
from apps.core.models import CorrelationEdge, PaymentAttempt, ProviderCall, UserRequest

_request = ContextVar("p24_request", default=None)
_operation = ContextVar("p24_operation", default=None)


def current_request():
    return _request.get()


def ensure_request(session, key, service_id=""):
    active = current_request()
    if active:
        if active.session_id != session.pk:
            raise PishkhanError("REQUEST_SESSION_MISMATCH", "Request belongs to another session.")
        if service_id and active.service_id and service_id != active.service_id:
            raise PishkhanError("REQUEST_SERVICE_MISMATCH", "Use a new request for a different service.")
        if service_id and not active.service_id:
            active.service_id = service_id
            active.save(update_fields=["service_id"])
        return active
    digest = hashlib.sha256(key.encode()).hexdigest()
    obj, _ = UserRequest.objects.get_or_create(
        session=session, client_key=digest, defaults={"service_id": service_id}
    )
    if service_id and obj.service_id and obj.service_id != service_id:
        raise PishkhanError("IDEMPOTENCY_CONFLICT", "Request key was already used for another service.")
    return obj


def get_request(session, request_id):
    try:
        return UserRequest.objects.get(pk=request_id, session=session)
    except (UserRequest.DoesNotExist, ValidationError, ValueError) as exc:
        raise PishkhanError("REQUEST_NOT_FOUND", "Request was not found in this session.") from exc


@contextmanager
def operation_scope(operation):
    r = _request.set(operation.request)
    o = _operation.set(operation)
    try:
        yield
    finally:
        _operation.reset(o)
        _request.reset(r)


@contextmanager
def tool_scope(arguments, requested_id=None):
    """Continue a quote/payment's request; never group by Session alone."""
    from apps.core import operations as ops

    session = ops.get_session(arguments["session_id"])
    inferred = None
    if arguments.get("quote_id"):
        inferred = ops.get_quote(session, arguments["quote_id"], allow_expired=True).request
    elif arguments.get("operation_id"):
        inferred = ops.get_operation(session, arguments["operation_id"]).request
    elif arguments.get("payment_key"):
        attempt = PaymentAttempt.objects.filter(session=session, payment_key=arguments["payment_key"]).first()
        inferred = attempt.request if attempt else None
    explicit = get_request(session, requested_id) if requested_id else None
    if explicit and inferred and explicit.pk != inferred.pk:
        raise PishkhanError("REQUEST_MISMATCH", "Continuation belongs to another request.")
    token = _request.set(explicit or inferred)
    try:
        yield explicit or inferred
    finally:
        _request.reset(token)


def _status_name(value):
    return value.get("Name", "") if isinstance(value, dict) else value if isinstance(value, str) else ""


def _bill_objects(value):
    """Never mistake Query.UniqueID or a generic item's ID for a BillUniqueID."""
    if isinstance(value, list):
        for item in value:
            yield from _bill_objects(item)
    elif isinstance(value, dict):
        if isinstance(value.get("UniqueID"), str) and ("Payment" in value or "PaymentStatus" in value):
            yield value
        else:
            for key in ("Bills", "Items", "Result"):
                yield from _bill_objects(value.get(key))


def observe(call, action, inputs, response):
    data = response.get("parameters")
    if not isinstance(data, dict):
        return
    endpoint = action["path"].split("/")[-1]

    def edge(source_type, source_key, target_type, target_key, evidence):
        if (
            not isinstance(source_key, str)
            or not isinstance(target_key, str)
            or not source_key
            or not target_key
        ):
            return
        CorrelationEdge.objects.create(
            session=call.session,
            request=call.request,
            call=call,
            source_type=source_type,
            source_key=source_key[:256],
            target_type=target_type,
            target_key=target_key[:256],
            evidence=evidence,
        )

    invoice = data.get("Invoice")
    purchase = inputs.get("PurchaseKey") or (
        invoice.get("PurchaseKey") if isinstance(invoice, dict) else None
    )
    if purchase and call.request_id:
        edge(
            "MCPRequest",
            str(call.request_id),
            "InvoiceID",
            purchase,
            "response.Invoice.PurchaseKey or request.PurchaseKey",
        )
    for bill in _bill_objects(data.get("Result")):
        edge(
            "InvoiceID",
            purchase,
            "BillUniqueID",
            bill["UniqueID"],
            "service response.Result; excludes Query.UniqueID",
        )
    key = data.get("PaymentKey")
    if key and endpoint in {"InvoicePayment", "BillsPayment"}:
        attempt, _ = PaymentAttempt.objects.get_or_create(
            session=call.session,
            payment_key=key,
            defaults={
                "request": call.request,
                "operation": call.operation,
                "purchase_key": purchase or "",
                "bill_ids": inputs.get("Bills", []),
                "gateway": inputs.get("Gateway", ""),
            },
        )
        edge("InvoiceID", purchase, "PaymentKey", key, "InvoicePayment request/response")
        for bill_id in inputs.get("Bills", []):
            edge("BillUniqueID", bill_id, "PaymentKey", key, "BillsPayment request/response")
    if endpoint == "PaymentInfo" and inputs.get("PaymentKey"):
        key = inputs["PaymentKey"]
        status = _status_name(data.get("Status")) or "Unknown"
        edge("PaymentKey", key, "PaymentStatus", status, "PaymentInfo.Status.Name (not callback URL)")
        edge("InvoiceID", purchase, "PaymentKey", key, "PaymentInfo.Invoice.PurchaseKey")
        bills = []
        for bill in _bill_objects(data.get("Bills")):
            bs = (
                bill.get("Payment", {}).get("Status")
                if isinstance(bill.get("Payment"), dict)
                else bill.get("PaymentStatus")
            )
            bills.append({"bill_id": bill["UniqueID"], "status": _status_name(bs) or "Unknown"})
            edge("BillUniqueID", bill["UniqueID"], "PaymentKey", key, "PaymentInfo.Bills")
            edge(
                "BillUniqueID",
                bill["UniqueID"],
                "BillPaymentStatus",
                bills[-1]["status"],
                "PaymentInfo.Bills[].Payment.Status",
            )
        PaymentAttempt.objects.filter(session=call.session, payment_key=key).update(
            status=status, bill_statuses=bills, updated_at=timezone.now()
        )


def trace_call(session, action, parameters, invoke):
    call = ProviderCall.objects.create(
        session=session, request=current_request(), operation=_operation.get(), action_id=action["id"]
    )
    started = perf_counter()
    try:
        result = invoke()
        call.status = "succeeded"
        call.upstream_code = str(result.get("status", {}).get("Code", ""))
        # Optional received metadata only; absent in the supplied HAR.
        call.upstream_request_id = str(result.get("upstream_request_id") or "")[:256]
        observe(call, action, parameters, result)
        return result
    except PishkhanError as exc:
        call.status = "unknown" if exc.details.get("outcome") == "unknown" else "failed"
        call.upstream_code = str(exc.details.get("upstream_code", ""))
        call.upstream_request_id = str(exc.details.get("upstream_request_id") or "")[:256]
        raise
    except Exception:
        call.status = "unknown"
        raise
    finally:
        call.duration_ms = round((perf_counter() - started) * 1000, 3)
        call.save(update_fields=["status", "upstream_code", "upstream_request_id", "duration_ms"])


def request_trace(session_id, request_id):
    from apps.core.operations import get_session

    request = get_request(get_session(session_id), request_id)
    return {
        **request.public_dict(),
        "upstream_request_id_note": "Core RequestID is recorded only when actually returned; none is exposed in the supplied HAR.",
        "operations": [
            {"operation_id": str(x.pk), "action_id": x.action_id, "status": x.status}
            for x in request.operations.order_by("created_at")
        ],
        "calls": [c.public_dict() for c in request.calls.order_by("created_at")],
        "correlations": [c.public_dict() for c in request.correlations.order_by("created_at")],
        "payments": [x.public_dict() for x in request.payments.order_by("pk")],
    }
