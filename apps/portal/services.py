"""Browser pilot presentation. Core remains the only financial authority."""

from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from apps.core.bills import recent_bills
from apps.core.models import AgentDailyUsage, Conversation, PaymentAttempt
from apps.core.payment_progress import payment_progress
from apps.core.tools import call_tool

from .models import PaymentSnapshot

# No raw upstream execution, session import, wallet debit, or card submission.
PILOT_TOOLS = frozenset(
    {
        "p24_begin_request",
        "p24_mobile_bill",
        "p24_electricity_bill",
        "p24_water_bill",
        "p24_recent_bills",
        "p24_run_inquiry",
        "p24_resume_inquiry",
        "p24_operation_status",
        "p24_bill_payment_options",
        "p24_bill_payment_link",
        "p24_payment_status",
    }
)
PILOT_PROMPT = """
This is a small invited LAN pilot, not the developer console.
Login is already managed by the browser. Never request login OTP/password in chat.
Available scope: electricity, water, mobile bills and their browser payment links/status.
Use only the advertised high-level tools; do not search unavailable raw endpoint contracts.
For a ready quote continue to p24_run_inquiry. Stop and explain any paid inquiry
prerequisite; do not debit a wallet. Bank payments are completed by the human.
Do not assume you can read browser history; recover previous bills with p24_recent_bills.
After a successful bill inquiry, the portal automatically prepares an IPG link
for a single positive unpaid bill. Do not ask for another user message to prepare
it, and do not call link tools again after this fresh inquiry. Multiple payable
terms require a selection. Explicit "inquiry only" or disabling the UI option
prevents automatic link preparation. Never submit a payment or debit a wallet.
A structured card displays the authoritative link and fees. DO NOT put payment
URLs, Markdown links or HTML in your reply; point to the payment card instead.
Never claim a link has succeeded before the structured result confirms it.
Keep replies brief and in Persian. Report partial progress and a clear next action on errors.
"""


def usage():
    limit = settings.AGENT_DAILY_MESSAGE_LIMIT
    used = (
        AgentDailyUsage.objects.filter(usage_date=timezone.localdate())
        .values_list("messages_used", flat=True)
        .first()
        or 0
    )
    return {"limit": limit, "used": used, "remaining": max(0, limit - used), "scope": "installation_daily"}


def safe_link(value):
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        if url.scheme == "https" and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


def remember_payment(visitor, payload):
    """Only store an observation of a PaymentKey that belongs to this account."""
    if not isinstance(payload, dict):
        return
    info = payload.get("payment_info") or payload
    key = info.get("payment_key")
    if (
        key
        and "payment_status" in info
        and PaymentAttempt.objects.filter(session=visitor.account, payment_key=key).exists()
    ):
        PaymentSnapshot.objects.update_or_create(visitor=visitor, payment_key=key, defaults={"data": info})


def result_error(payload):
    if not isinstance(payload, dict):
        return None
    inner = payload.get("result")
    return payload.get("error") or (inner.get("error") if isinstance(inner, dict) else None)


def state(visitor):
    account = visitor.account
    authenticated = bool(account and account.state == "authenticated")
    result = {
        "ok": True,
        "mode": account.mode if account else settings.P24_MODE,
        "account": {
            "state": account.state if account else "guest",
            "phone": account.phone if account else "",
        },
        "authenticated": authenticated,
        "auto_payment_links": settings.P24_AUTO_BILL_LINKS,
        "agent_configured": bool(settings.AGENT_BASE_URL and settings.AGENT_MODEL),
        "usage": usage(),
        "busy": bool(visitor.active_turn),
        "conversations": [],
        "bills": [],
        "payments": [],
    }
    if not authenticated:
        return result
    result["conversations"] = [
        {
            "id": str(c.pk),
            "title": next(
                (str(m.get("content") or "")[:70] for m in c.messages if m.get("role") == "user"), ""
            ),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in Conversation.objects.filter(session=account).order_by("-updated_at")[:30]
    ]
    attempts = list(PaymentAttempt.objects.filter(session=account).order_by("-updated_at")[:30])
    result["payments"] = payment_cards(visitor)
    result["bills"] = recent_bills(str(account.pk), limit=20)["items"]
    for b in result["bills"]:
        related = next((p for p in attempts if b["bill_id"] in p.bill_ids), None)
        if related:
            b["payment_key"] = related.payment_key
            b["current_payment_status"] = related.status
            b["payment_complete"] = payment_progress(related)["payment_complete"]
        # This is a stored observation; the UI must not call it a new inquiry.
    return result


def payment_cards(visitor, keys=None):
    account = visitor.account
    if not account or account.state != "authenticated":
        return []
    cards = []
    snapshots = {s.payment_key: s for s in PaymentSnapshot.objects.filter(visitor=visitor)}
    attempts_query = PaymentAttempt.objects.filter(session=account).select_related("operation")
    if keys is not None:
        attempts_query = attempts_query.filter(payment_key__in=keys)
    attempts = list(attempts_query.order_by("-updated_at")[:30])
    for p in attempts:
        progress = payment_progress(p)
        raw = p.operation.result if p.operation else {}
        snap = snapshots.get(p.payment_key)
        data = snap.data if snap else {}
        cards.append(
            {
                "payment_key": p.payment_key,
                "bill_ids": p.bill_ids,
                "last_checked_at": snap.observed_at.isoformat() if snap else None,
                "payment_status": p.status,
                **progress,
                "gateway": p.gateway,
                "observed_at": p.updated_at.isoformat(),
                "amount": data.get("amount"),
                "fee": data.get("fee"),
                "total_amount": data.get("total_amount"),
                "currency": "IRR",
                "amounts_observed_at": snap.observed_at.isoformat() if snap else None,
                "redirect_url": safe_link((raw.get("parameters") or {}).get("RedirectLink"))
                if p.status == "Unpaid"
                else None,
            }
        )
    if keys is not None:
        cards = [card for card in cards if card["payment_key"] in keys]
    return cards


def status_message(info):
    if info.get("payment_complete"):
        return "\u067e\u0631\u062f\u0627\u062e\u062a \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f. \u0646\u06cc\u0627\u0632\u06cc \u0628\u0647 \u067e\u0631\u062f\u0627\u062e\u062a \u0645\u062c\u062f\u062f \u0646\u06cc\u0633\u062a."
    if info.get("payment_status") == "Unpaid":
        return "\u0648\u0636\u0639\u06cc\u062a \u0627\u0632 \u067e\u06cc\u0634\u062e\u0648\u0627\u0646 \u062f\u0631\u06cc\u0627\u0641\u062a \u0634\u062f\u061b \u0647\u0646\u0648\u0632 \u067e\u0631\u062f\u0627\u062e\u062a\u06cc \u0628\u0631\u0627\u06cc \u0627\u06cc\u0646 \u062a\u0631\u0627\u06a9\u0646\u0634 \u062b\u0628\u062a \u0646\u0634\u062f\u0647 \u0627\u0633\u062a."
    if info.get("payment_confirmed"):
        return "\u067e\u0631\u062f\u0627\u062e\u062a \u062b\u0628\u062a \u0634\u062f\u0647 \u0627\u0633\u062a\u061b \u0646\u062a\u06cc\u062c\u0647 \u0647\u0645\u0647 \u0642\u0628\u0636\u200c\u0647\u0627 \u0647\u0646\u0648\u0632 \u0646\u0647\u0627\u06cc\u06cc \u0646\u06cc\u0633\u062a. \u067e\u0631\u062f\u0627\u062e\u062a \u0631\u0627 \u062a\u06a9\u0631\u0627\u0631 \u0646\u06a9\u0646\u06cc\u062f."
    return "\u0648\u0636\u0639\u06cc\u062a \u062f\u0631\u06cc\u0627\u0641\u062a \u0634\u062f\u061b \u0646\u062a\u06cc\u062c\u0647 \u067e\u0631\u062f\u0627\u062e\u062a \u0647\u0646\u0648\u0632 \u0642\u0637\u0639\u06cc \u0646\u06cc\u0633\u062a. \u067e\u0631\u062f\u0627\u062e\u062a \u062c\u062f\u06cc\u062f \u0646\u0633\u0627\u0632\u06cc\u062f."


def invoke(visitor, name, arguments):
    payload = call_tool(name, {**arguments, "session_id": str(visitor.account_id)})
    remember_payment(visitor, payload)
    return payload
