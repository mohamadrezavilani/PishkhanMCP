"""Recover stored inquiry results and create browser-only payment links.

These helpers never infer bill identifiers from a phone number or a Query ID.
The old shared-endpoint label is preserved as evidence, not silently rewritten.
"""

import hashlib
import json

from apps.core import operations as ops
from apps.core import payments
from apps.core.errors import PishkhanError
from apps.core.models import Operation, Quote
from apps.core.tracing import _bill_objects, current_request, tool_scope
from apps.providers.registry import find_action, get_action
from apps.providers.service_mapping import MOBILE_OPERATORS


def _saved_bills(session):
    rows = (
        Operation.objects.filter(
            session=session, status=Operation.Status.COMPLETED, action_id__startswith="services_"
        )
        .select_related("request")
        .order_by("-created_at", "-id")
    )
    for operation in rows.iterator(chunk_size=100):
        if not isinstance(operation.result, dict):
            continue
        data = operation.result.get("parameters", {})
        if (
            not isinstance(data, dict)
            or not isinstance(operation.result.get("status"), dict)
            or str(operation.result["status"].get("Code", "")).upper() != "G00000"
        ):
            continue
        bills = list(_bill_objects(data.get("Result")))
        if not bills:
            continue
        query = data.get("Query") or {}
        if not isinstance(query, dict):
            continue
        inputs = {
            x.get("Key"): x.get("Value") for x in (query.get("Parameters") or []) if isinstance(x, dict)
        }
        quote = Quote.objects.filter(session=session, operation=operation).first()
        try:
            names = get_action(operation.action_id).get("frontend_service_names", [])
        except PishkhanError:
            continue
        service_name = (
            quote.parameters.get("service_name") if quote else names[0] if len(names) == 1 else None
        )
        operator = str(inputs.get("Operator", "")).casefold()
        effective_service = operator if operator in MOBILE_OPERATORS else operation.service_id
        for bill in bills:
            if "Amount" not in bill:
                continue
            yield {
                "bill_id": bill["UniqueID"],
                "operation_id": str(operation.pk),
                "request_id": str(operation.request_id) if operation.request_id else None,
                "quote_id": str(quote.pk) if quote else None,
                "service_id": effective_service,
                "recorded_service_id": operation.service_id,
                "service_name": service_name,
                "line_number": inputs.get("LineNumber"),
                "amount": bill.get("Amount"),
                "currency": "IRR",
                "payment_status": (bill.get("Payment") or {}).get("Status", {}).get("Name", "Unknown"),
                "final_term": (bill.get("ExtraInfo") or {}).get("Final"),
                "observed_at": operation.created_at.isoformat(),
                "bill_datetime": bill.get("DateTime"),
                "source": "stored_operation_result",
                "fresh_inquiry": False,
            }


def recent_bills(session_id, service_id=None, phone=None, offset=0, limit=10):
    """Session-scoped, paginated local retrieval; no upstream/model call."""
    session = ops.get_session(session_id)
    request = current_request()
    normalized_phone = ops.digits(phone) if phone else None
    items = []
    seen = set()
    for record in _saved_bills(session):
        if request and record["request_id"] != str(request.pk):
            continue
        if service_id and record["service_id"] != service_id:
            continue
        if normalized_phone and record["line_number"] != normalized_phone:
            continue
        if record["bill_id"] in seen:
            continue
        seen.add(record["bill_id"])
        items.append(record)
        if len(items) > offset + limit:
            break
    return {
        "items": items[offset : offset + limit],
        "next_offset": offset + limit if len(items) > offset + limit else None,
        "fresh_inquiry": False,
        "notice": "Stored observations, not current debt verification. Use the exact BillUniqueID, not Query.UniqueID.",
    }


def _subjects(session, bill_ids):
    wanted = set(bill_ids)
    found = {}
    request = current_request()
    for record in _saved_bills(session):
        if request and record["request_id"] != str(request.pk):
            continue
        if record["bill_id"] in wanted and record["bill_id"] not in found:
            found[record["bill_id"]] = record
        if len(found) == len(wanted):
            break
    if len(found) != len(wanted):
        raise PishkhanError("BILL_NOT_FOUND", "Recover this session's original bill with p24_recent_bills.")
    subjects = [found[key] for key in sorted(wanted)]
    requests = {x["request_id"] for x in subjects}
    services = {x["service_name"] for x in subjects}
    if len(requests) != 1 or None in requests or len(services) != 1 or None in services:
        raise PishkhanError("BILL_CONTEXT_AMBIGUOUS", "Use bills from one known inquiry request and Service.")
    return subjects


def bill_payment_options(session_id, bill_ids):
    session = ops.get_session(session_id)
    subjects = _subjects(session, bill_ids)
    service_name = subjects[0]["service_name"]
    with tool_scope({"session_id": session_id}, subjects[0]["request_id"]):
        result = ops.live_call(
            session,
            find_action("BillsPaymentChannels", "core"),
            {"Service": service_name, "Bills": sorted(set(bill_ids))},
        )
    channels = result.get("parameters", {}).get("PaymentChannels", [])
    names = sorted(payments.gateway_names(channels))
    # Only recognized browser gateway families; never substitute a wallet/CNPG.
    browser = [name for name in names if name.casefold().startswith(("onlinepayment_", "ipg_"))]
    return {
        "request_id": subjects[0]["request_id"],
        "service_name": service_name,
        "bills": subjects,
        "gateways": names,
        "browser_gateways": browser,
        "payment_channels": channels,
        "fee": None,
        "total_amount": None,
        "notice": "Channel discovery does not quote a fee. PaymentInfo provides authoritative amounts after preparation.",
    }


def bill_payment_link(session_id, bill_ids, idempotency_key):
    """Prepare IPG only. Never submit card details, payment OTP or debit a wallet."""
    session = ops.get_session(session_id)
    if session.mode != "live":
        raise PishkhanError("LIVE_ACTION_ONLY", "Use the demo payment tools for simulation.")
    subjects = _subjects(session, bill_ids)
    if any(
        x["payment_status"] != "Unpaid" or not isinstance(x["amount"], int) or x["amount"] <= 0
        for x in subjects
    ):
        raise PishkhanError("BILL_NOT_PAYABLE", "Only positive unpaid stored bills may start this link flow.")
    with tool_scope({"session_id": session_id}, subjects[0]["request_id"]):
        stable_key = "bills:" + hashlib.sha256(json.dumps(sorted(set(bill_ids))).encode()).hexdigest()
        prior = (
            Operation.objects.select_related("session")
            .filter(session=session, idempotency_key=stable_key)
            .first()
        )
        if prior and prior.request_id and str(prior.request_id) != subjects[0]["request_id"]:
            raise PishkhanError("REQUEST_MISMATCH", "The bill reservation belongs to another request.")
        if prior and prior.status != Operation.Status.FAILED:
            result = ops._operation_response(prior, replayed=True)
        else:
            options = bill_payment_options(session_id, bill_ids)
            if not options["browser_gateways"]:
                raise PishkhanError(
                    "BROWSER_GATEWAY_UNAVAILABLE", "No active browser IPG; wallet/CNPG not substituted."
                )
            old_gateway = prior.request_data.get("Gateway") if prior else None
            gateway = (
                old_gateway if old_gateway in options["browser_gateways"] else options["browser_gateways"][0]
            )
            result = payments.prepare_bill_payment(
                session_id, bill_ids, gateway, idempotency_key, subjects[0]["service_name"]
            )
        if not result.get("ok"):
            return result
        payment_key = result.get("result", {}).get("payment_key")
        if payment_key:
            try:
                result["payment_info"] = payments.payment_status(session_id, payment_key)
            except PishkhanError as exc:
                result["payment_info_error"] = exc.as_dict()["error"]
        result["bills"] = subjects
        result["notice"] = (
            "Link prepared only. Review PaymentInfo amounts and the bank page; no payment was submitted by this tool."
        )
        return result
