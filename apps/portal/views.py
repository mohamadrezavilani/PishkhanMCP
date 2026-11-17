import hashlib
import json
import logging
import re
import uuid
from datetime import timedelta
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.agent.redaction import redact
from apps.agent.runner import run_turn
from apps.core.errors import PishkhanError
from apps.core.models import AccountSession, Conversation
from apps.core.operations import digits
from apps.core.tools import call_tool

from .checkout import link_preparation_enabled, payment_keys, prepare_inquiry_links
from .models import ChatTurn, Feedback, Visitor
from .services import (
    PILOT_PROMPT,
    PILOT_TOOLS,
    invoke,
    payment_cards,
    remember_payment,
    result_error,
    state,
    status_message,
)

logger = logging.getLogger(__name__)


def respond(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def failure(code, message, status=400):
    return respond({"ok": False, "error": {"code": code, "message": message}}, status)


def data(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise PishkhanError("INVALID_JSON", "Invalid request body.") from exc
    if not isinstance(payload, dict):
        raise PishkhanError("INVALID_JSON", "An object is required.")
    if any(k in payload for k in ("session_id", "visitor_id", "account_id")):
        raise PishkhanError("BROWSER_SESSION_REQUIRED", "Account is bound to this browser, not request data.")
    return payload


def visitor_for(request):
    key = request.session.get("portal_visitor")
    visitor = Visitor.objects.select_related("account").filter(pk=key).first() if key else None
    if visitor is None:
        visitor = Visitor.objects.create()
        request.session["portal_visitor"] = str(visitor.pk)
    return visitor


def api(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        try:
            return view(request, visitor_for(request), *args, **kwargs)
        except PishkhanError as exc:
            return respond(exc.as_dict(), 400)
        except (ValidationError, ValueError, TypeError):
            return failure(
                "INVALID_INPUT",
                "\u0648\u0631\u0648\u062f\u06cc \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u06cc\u062f.",
            )

    return inner


def connected(visitor):
    if not visitor.account_id or visitor.account.state != "authenticated":
        raise PishkhanError(
            "LOGIN_REQUIRED",
            "\u0627\u0628\u062a\u062f\u0627 \u0627\u0632 \u0628\u062e\u0634 \u0648\u0631\u0648\u062f\u060c \u062d\u0633\u0627\u0628 \u062e\u0648\u062f \u0631\u0627 \u0645\u062a\u0635\u0644 \u06a9\u0646\u06cc\u062f.",
        )


@require_GET
@ensure_csrf_cookie
def index(request):
    return render(request, "portal.html", {"mode": settings.P24_MODE})


@require_GET
def asset(request, name):
    if name not in {"pilot.css", "pilot.js"}:
        return failure("NOT_FOUND", "Not found", 404)
    path = Path(__file__).parent / "assets" / name
    result = HttpResponse(
        path.read_bytes(), content_type="text/css" if name.endswith(".css") else "text/javascript"
    )
    result["Cache-Control"] = "no-cache"
    return result


@require_GET
@api
def bootstrap(request, visitor):
    return respond(state(visitor))


@require_POST
@api
def send_otp(request, visitor):
    payload = data(request)
    phone = digits(payload.get("phone", ""))
    if not re.fullmatch(r"09[0-9]{9}", phone):
        return failure(
            "PHONE_INVALID",
            "\u0634\u0645\u0627\u0631\u0647 \u0645\u0648\u0628\u0627\u06cc\u0644 \u06f1\u06f1 \u0631\u0642\u0645\u06cc \u0628\u0627 \u06f0\u06f9 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f.",
        )
    if visitor.active_turn:
        return failure("TURN_RUNNING", "A request is still running.", 409)
    if visitor.account_id and visitor.account.state == "authenticated":
        return failure("ALREADY_CONNECTED", "Sign out before changing accounts.", 409)
    now = timezone.now()
    # Reserve the SMS cooldown atomically. Failed sends are not immediately replayed.
    changed = (
        Visitor.objects.filter(pk=visitor.pk)
        .filter(Q(otp_sent_at__isnull=True) | Q(otp_sent_at__lte=now - timedelta(seconds=60)))
        .update(otp_sent_at=now)
    )
    if not changed:
        return failure(
            "OTP_COOLDOWN",
            "\u0628\u0631\u0627\u06cc \u0627\u0631\u0633\u0627\u0644 \u0645\u062c\u062f\u062f \u06a9\u062f\u060c \u06f6\u06f0 \u062b\u0627\u0646\u06cc\u0647 \u0641\u0627\u0635\u0644\u0647 \u0644\u0627\u0632\u0645 \u0627\u0633\u062a.",
            429,
        )
    if not visitor.account_id or visitor.account.state in {"closed", "expired"} or not visitor.account.token:
        created = call_tool("p24_create_session", {})
        if created.get("bootstrap") not in {None, "completed"}:
            return respond(
                {"ok": False, "error": created.get("bootstrap_error", {"code": "BOOTSTRAP_FAILED"})}, 502
            )
        if not created.get("ok"):
            return respond(created, 502)
        visitor.account = AccountSession.objects.get(pk=created["session_id"])
        visitor.save(update_fields=["account"])
    response = invoke(
        visitor, "p24_request_otp", {"phone": phone, "idempotency_key": "portal-send-" + str(uuid.uuid4())}
    )
    if not response.get("ok"):
        return respond({"ok": False, "error": result_error(response) or {"code": "OTP_FAILED"}}, 400)
    return respond(
        {"ok": True, "phone": phone, "state": "otp_pending", "mode": visitor.account.mode, "resend_after": 60}
    )


@require_POST
@api
def verify_otp(request, visitor):
    payload = data(request)
    if not visitor.account_id or visitor.account.state != "otp_pending":
        return failure("OTP_NOT_REQUESTED", "Request a code first.")
    otp = digits(payload.get("otp", ""))
    if not re.fullmatch(r"[0-9]{4,8}", otp):
        return failure(
            "OTP_INVALID",
            "\u06a9\u062f \u062f\u0631\u06cc\u0627\u0641\u062a\u200c\u0634\u062f\u0647 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f.",
        )
    response = invoke(
        visitor,
        "p24_verify_otp",
        {"phone": visitor.account.phone, "otp": otp, "idempotency_key": "portal-verify-" + str(uuid.uuid4())},
    )
    if not response.get("ok"):
        return respond({"ok": False, "error": result_error(response) or {"code": "LOGIN_FAILED"}}, 400)
    request.session.cycle_key()
    visitor.refresh_from_db()
    return respond(state(visitor))


@require_POST
@api
def logout(request, visitor):
    data(request)
    if visitor.active_turn:
        return failure(
            "TURN_RUNNING", "A request is still running. Check its result before signing out.", 409
        )
    if visitor.account_id:
        call_tool("p24_close_session", {"session_id": str(visitor.account_id)})
    request.session.flush()
    return respond({"ok": True})


@require_GET
@api
def history(request, visitor, conversation_id):
    connected(visitor)
    row = Conversation.objects.filter(pk=conversation_id, session=visitor.account).first()
    if row is None:
        return failure("CONVERSATION_NOT_FOUND", "Conversation not found in this account.", 404)
    messages = [
        {"role": m["role"], "content": m.get("content") or ""}
        for m in row.messages
        if m.get("role") in {"user", "assistant"} and m.get("content")
    ]
    keys = set()
    for m in row.messages:
        if m.get("role") == "tool":
            try:
                keys.update(payment_keys(json.loads(m.get("content") or "{}")))
            except (ValueError, TypeError):
                pass
    for turn in ChatTurn.objects.filter(visitor=visitor, response__conversation_id=str(row.pk)):
        keys.update(turn.response.get("payment_keys", []))
    # Rebuild from this account's current observations, not stale card snapshots.
    cards = payment_cards(visitor, keys)
    return respond(
        {
            "ok": True,
            "conversation_id": str(row.pk),
            "messages": redact(messages),
            "payment_cards": cards,
            "payment_keys": [c["payment_key"] for c in cards],
        }
    )


@require_POST
@api
def chat(request, visitor):
    connected(visitor)
    payload = data(request)
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return failure("MESSAGE_INVALID", "Message must contain 1-4000 characters.")
    if not settings.AGENT_BASE_URL or not settings.AGENT_MODEL:
        return failure(
            "agent_not_configured",
            "\u0645\u062f\u0644 \u06af\u0641\u062a\u200c\u0648\u06af\u0648 \u0647\u0646\u0648\u0632 \u062a\u0648\u0633\u0637 \u0645\u0633\u0626\u0648\u0644 \u067e\u0631\u0648\u0698\u0647 \u062a\u0646\u0638\u06cc\u0645 \u0646\u0634\u062f\u0647 \u0627\u0633\u062a.",
        )
    key = uuid.UUID(str(payload.get("client_key", "")))
    conversation_id = payload.get("conversation_id") or None
    if (
        conversation_id
        and not Conversation.objects.filter(pk=conversation_id, session=visitor.account).exists()
    ):
        return failure("CONVERSATION_NOT_FOUND", "Conversation not found in this account.", 404)
    auto_link = payload.get("auto_payment_link", settings.P24_AUTO_BILL_LINKS)
    if type(auto_link) is not bool:
        return failure("INVALID_INPUT", "auto_payment_link must be a boolean.")
    fingerprint_data = [message, conversation_id]
    if "auto_payment_link" in payload:
        fingerprint_data.append(auto_link)
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data, ensure_ascii=False).encode()).hexdigest()
    prior = ChatTurn.objects.filter(visitor=visitor, client_key=key).first()
    if prior:
        if prior.fingerprint != fingerprint:
            return failure("TURN_KEY_CONFLICT", "Use a new key for a new message.", 409)
        if prior.state == "running":
            return respond(
                {
                    "ok": False,
                    "error": {"code": "TURN_RUNNING", "message": "The original turn is still running."},
                    "turn_id": str(prior.pk),
                },
                409,
            )
        return respond(
            {
                **prior.response,
                "payment_cards": payment_cards(visitor, set(prior.response.get("payment_keys", []))),
                "replayed": True,
            }
        )
    try:
        with transaction.atomic():
            turn_id = uuid.uuid4()
            if not Visitor.objects.filter(pk=visitor.pk, active_turn="").update(active_turn=str(turn_id)):
                return failure(
                    "TURN_RUNNING",
                    "\u067e\u0627\u0633\u062e \u067e\u06cc\u0627\u0645 \u0642\u0628\u0644\u06cc \u0647\u0646\u0648\u0632 \u062f\u0631 \u062d\u0627\u0644 \u0622\u0645\u0627\u062f\u0647\u200c\u0634\u062f\u0646 \u0627\u0633\u062a.",
                    409,
                )
            turn = ChatTurn.objects.create(
                id=turn_id, visitor=visitor, client_key=key, fingerprint=fingerprint
            )
    except IntegrityError:
        # A replay can arrive just after the first turn released its lease.
        # The unique client key won; never start a second model turn.
        prior = ChatTurn.objects.filter(visitor=visitor, client_key=key).first()
        if prior and prior.fingerprint == fingerprint and prior.state != "running":
            return respond(
                {
                    **prior.response,
                    "payment_cards": payment_cards(visitor, set(prior.response.get("payment_keys", []))),
                    "replayed": True,
                }
            )
        return failure("TURN_RUNNING", "The original turn is already reserved.", 409)
    try:
        result = run_turn(
            str(visitor.account_id),
            message,
            conversation_id,
            tool_names=PILOT_TOOLS,
            extra_instructions=PILOT_PROMPT,
        )
        trace = list(result.get("tool_calls", []))
        for entry in trace:
            remember_payment(visitor, entry.get("result", {}))
        automatic = prepare_inquiry_links(
            visitor, trace, enabled=link_preparation_enabled(message, auto_link)
        )
        trace.extend(automatic["entries"])
        keys = set(automatic["payment_keys"])
        for entry in trace:
            keys.update(payment_keys(entry.get("result", {})))
        response = {
            key: result[key]
            for key in ("ok", "reply", "conversation_id", "steps", "stop_reason", "error", "agent_usage")
            if key in result
        }
        response["activity"] = [
            {
                "name": t["name"],
                "ok": t.get("result", {}).get("ok", False),
                "error_code": (result_error(t.get("result", {})) or {}).get("code"),
            }
            for t in trace
        ]
        response["payment_cards"] = payment_cards(visitor, keys)
        response["payment_keys"] = [c["payment_key"] for c in response["payment_cards"]]
        response["notices"] = automatic["notices"]
        response["turn_id"] = str(turn.pk)
        turn.state = "completed"
    except Exception as exc:
        # Do not retry an uncertain turn. Domain operation records remain intact.
        logger.error("Portal turn %s interrupted (%s)", turn.pk, type(exc).__name__)
        response = {
            "ok": False,
            "error": {
                "code": "TURN_INTERRUPTED",
                "message": "\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0645\u062a\u0648\u0642\u0641 \u0634\u062f. \u0627\u0628\u062a\u062f\u0627 \u0633\u0648\u0627\u0628\u0642 \u0648 \u067e\u0631\u062f\u0627\u062e\u062a\u200c\u0647\u0627 \u0631\u0627 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u06cc\u062f.",
            },
            "turn_id": str(turn.pk),
        }
        turn.state = "unknown"
    finally:
        # DB write failure must keep the lease; never silently reissue an unknown turn.
        if "response" in locals():
            turn.response = response
            turn.save(update_fields=["state", "response", "updated_at"])
            Visitor.objects.filter(pk=visitor.pk, active_turn=str(turn.pk)).update(active_turn="")
    return respond(response, 200 if response.get("ok") else 400)


@require_GET
@api
def turn_status(request, visitor, client_key):
    row = ChatTurn.objects.filter(visitor=visitor, client_key=client_key).first()
    if row is None:
        return failure("TURN_NOT_FOUND", "Turn not found.", 404)
    return respond({"ok": True, "state": row.state, "result": row.response})


@require_POST
@api
def payment_action(request, visitor):
    connected(visitor)
    if visitor.active_turn:
        return failure("TURN_RUNNING", "Wait for the active chat turn before another action.", 409)
    payload = data(request)
    action = payload.get("action")
    if action == "status":
        key = payload.get("payment_key")
        if not isinstance(key, str) or not key or len(key) > 256:
            return failure("PAYMENT_KEY_REQUIRED", "Payment key required.")
        result = invoke(visitor, "p24_payment_status", {"payment_key": key})
    elif action == "link":
        ids = payload.get("bill_ids")
        if (
            not isinstance(ids, list)
            or not 1 <= len(ids) <= 10
            or any(not isinstance(b, str) or not 1 <= len(b) <= 128 for b in ids)
        ):
            return failure("BILLS_REQUIRED", "Select bills from this browser's history.")
        result = invoke(
            visitor,
            "p24_bill_payment_link",
            {
                "bill_ids": ids,
                "idempotency_key": "portal-link-"
                + hashlib.sha256(json.dumps(sorted(set(ids))).encode()).hexdigest(),
            },
        )
    else:
        return failure("UNKNOWN_ACTION", "Only a link or status read is available.")
    if not result.get("ok"):
        return respond({"ok": False, "error": result_error(result) or {"code": "PAYMENT_FAILED"}}, 400)
    visitor.refresh_from_db()
    update = state(visitor)
    info = result.get("payment_info") or result
    checked_key = info.get("payment_key") or result.get("result", {}).get("payment_key")
    update["payment_update"] = {
        "payment_key": checked_key,
        "action": action,
        "checked_at": timezone.now().isoformat(),
        "message": status_message(info)
        if action == "status"
        else "\u0644\u06cc\u0646\u06a9 \u067e\u0631\u062f\u0627\u062e\u062a \u0622\u0645\u0627\u062f\u0647 \u0627\u0633\u062a\u061b \u0645\u0628\u0644\u063a \u0646\u0647\u0627\u06cc\u06cc \u0631\u0627 \u062f\u0631 \u06a9\u0627\u0631\u062a \u0628\u0628\u06cc\u0646\u06cc\u062f.",
        "payment_complete": info.get("payment_complete", False),
    }
    return respond(update)


@require_POST
@api
def feedback(request, visitor):
    connected(visitor)
    payload = data(request)
    rating = payload.get("rating")
    comment = payload.get("comment", "")
    if type(rating) is not int or not 1 <= rating <= 5 or not isinstance(comment, str) or len(comment) > 2000:
        return failure("FEEDBACK_INVALID", "Rating 1-5 and up to 2000 characters are required.")
    Feedback.objects.create(visitor=visitor, rating=rating, comment=comment)
    return respond({"ok": True})
