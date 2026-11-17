"""Prepare IPG links for a just-completed inquiry; never submit money.

Called only during a reserved chat turn, never by state/history GETs. Real
stored results, account ownership and the core bill reservation are authoritative.
"""

import logging
import uuid
from collections import defaultdict

from apps.core.bills import _saved_bills
from apps.core.models import Operation, PaymentAttempt

from .services import invoke, result_error

logger = logging.getLogger(__name__)

INQUIRY_ACTIONS = frozenset(
    {"services_cell_phone_bills_v1", "services_electric_bills_v1", "services_water_bills_v1"}
)


def link_preparation_enabled(message, enabled):
    """A UI opt-out plus conservative explicit inquiry-only phrases, not intent inference."""
    normalized = " ".join(str(message).replace("\u200c", " ").split()).casefold()
    blockers = (
        "\u0641\u0642\u0637 \u0627\u0633\u062a\u0639\u0644\u0627\u0645",
        "\u0628\u062f\u0648\u0646 \u0644\u06cc\u0646\u06a9",
        "\u0644\u06cc\u0646\u06a9 \u0646\u0633\u0627\u0632",
        "\u0644\u06cc\u0646\u06a9 \u067e\u0631\u062f\u0627\u062e\u062a \u0646\u0633\u0627\u0632",
        "no payment link",
        "inquiry only",
        "do not create a payment link",
    )
    return bool(enabled) and not any(value in normalized for value in blockers)


def payment_keys(payload):
    """Read keys only from structured tool results (not model prose/URLs)."""
    if not isinstance(payload, dict):
        return set()
    keys = set()
    value = payload.get("payment_key")
    if isinstance(value, str) and 0 < len(value) <= 256:
        keys.add(value)
    for field in ("result", "payment_info", "payment_state"):
        if isinstance(payload.get(field), dict):
            keys.update(payment_keys(payload[field]))
    return keys


def prepare_inquiry_links(visitor, trace, *, enabled=True):
    prepared, notices, ids, existing_keys = [], [], set(), set()
    if not enabled or not visitor.account_id or visitor.account.mode != "live":
        return {"entries": prepared, "notices": notices, "payment_keys": sorted(existing_keys)}
    for entry in trace:
        if entry.get("name") not in {
            "p24_run_inquiry",
            "p24_mobile_bill",
            "p24_electricity_bill",
            "p24_water_bill",
        }:
            continue
        payload = entry.get("result", {})
        if not isinstance(payload, dict) or not payload.get("ok"):
            continue
        try:
            ids.add(uuid.UUID(str(payload.get("operation_id", ""))))
        except ValueError:
            continue
    rows = Operation.objects.filter(
        session=visitor.account,
        pk__in=ids,
        status=Operation.Status.COMPLETED,
        action_id__in=INQUIRY_ACTIONS,
    )
    groups = defaultdict(list)
    for bill in _saved_bills(visitor.account, operation_ids=list(rows.values_list("pk", flat=True))):
        if bill["payment_status"] == "Unpaid" and type(bill["amount"]) is int and bill["amount"] > 0:
            groups[bill["operation_id"]].append(bill)
    seen = set()
    for bills in list(groups.values())[:5]:
        # Mid-term/end-term amounts can overlap. Never choose/pay both implicitly.
        distinct = {b["bill_id"]: b for b in bills}
        if len(distinct) != 1:
            notices.append(
                {
                    "code": "BILL_SELECTION_REQUIRED",
                    "message": "\u0686\u0646\u062f \u0642\u0628\u0636 \u06cc\u0627 \u062f\u0648\u0631\u0647 \u0628\u0631\u06af\u0634\u062a\u0647 \u0627\u0633\u062a\u061b \u0628\u0631\u0627\u06cc \u0633\u0627\u062e\u062a \u0644\u06cc\u0646\u06a9\u060c \u0642\u0628\u0636 \u0645\u0648\u0631\u062f\u0646\u0638\u0631 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f.",
                }
            )
            continue
        bill = next(iter(distinct.values()))
        if bill["bill_id"] in seen:
            continue
        seen.add(bill["bill_id"])
        attempts = PaymentAttempt.objects.filter(session=visitor.account)
        matches = [a for a in attempts.iterator() if bill["bill_id"] in (a.bill_ids or [])]
        if matches:
            existing_keys.update(a.payment_key for a in matches)
            # Existing/uncertain payments remain available as status cards. No new intent.
            continue
        try:
            payload = invoke(
                visitor,
                "p24_bill_payment_link",
                {
                    "bill_ids": [bill["bill_id"]],
                    "request_id": bill["request_id"],
                    "idempotency_key": "portal-auto-" + bill["bill_id"],
                },
            )
        except Exception as exc:
            logger.error("Automatic link interrupted (%s)", type(exc).__name__)
            payload = {
                "ok": False,
                "error": {
                    "code": "AUTO_LINK_INTERRUPTED",
                    "message": "Link outcome unknown; inspect existing operations before retrying.",
                },
            }
        prepared.append({"name": "p24_bill_payment_link", "result": payload, "automatic": True})
        error = result_error(payload)
        if not payload.get("ok"):
            notices.append(
                {
                    "code": (error or {}).get("code", "LINK_NOT_READY"),
                    "message": "\u0627\u0633\u062a\u0639\u0644\u0627\u0645 \u0627\u0646\u062c\u0627\u0645 \u0634\u062f\u060c \u0627\u0645\u0627 \u0644\u06cc\u0646\u06a9 \u067e\u0631\u062f\u0627\u062e\u062a \u0622\u0645\u0627\u062f\u0647 \u0646\u0634\u062f. \u0646\u062a\u06cc\u062c\u0647 \u0642\u0628\u0636 \u062f\u0631 \u0633\u0648\u0627\u0628\u0642 \u0645\u062d\u0641\u0648\u0638 \u0627\u0633\u062a.",
                }
            )
    return {"entries": prepared, "notices": notices, "payment_keys": sorted(existing_keys)}
