import json
import secrets
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.errors import PishkhanError
from apps.core.operations import get_session
from apps.core.tools import call_tool, list_tools


def api_access(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        key = settings.P24_ACCESS_KEY
        supplied = request.headers.get("Authorization", "")
        if key and not secrets.compare_digest(supplied, f"Bearer {key}"):
            return JsonResponse(
                {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "Bearer access key required."}},
                status=401,
            )
        try:
            return view(request, *args, **kwargs)
        except PishkhanError as exc:
            return JsonResponse(exc.as_dict(), status=400, json_dumps_params={"ensure_ascii": False})

    return wrapped


def body(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise PishkhanError("INVALID_JSON", "بدنهٔ درخواست JSON معتبر نیست.") from exc
    if not isinstance(payload, dict):
        raise PishkhanError("INVALID_JSON", "بدنهٔ درخواست باید یک object باشد.")
    return payload


def respond(value, status=200):
    return JsonResponse(value, status=status, json_dumps_params={"ensure_ascii": False})


@require_GET
def index(request):
    return render(
        request,
        "index.html",
        {
            "mode": settings.P24_MODE,
            "agent_configured": bool(settings.AGENT_BASE_URL and settings.AGENT_MODEL),
            "access_key_required": bool(settings.P24_ACCESS_KEY),
        },
    )


@require_GET
def health(request):
    return respond({"ok": True, "application": "PishkhanMCP", "version": "0.1.0", "mode": settings.P24_MODE})


@require_GET
@api_access
def tools_list(request):
    return respond({"tools": list_tools()})


@csrf_exempt
@require_POST
@api_access
def tools_call(request):
    payload = body(request)
    if not isinstance(payload.get("name"), str) or not isinstance(payload.get("arguments", {}), dict):
        raise PishkhanError("INVALID_REQUEST", "name و arguments معتبر لازم است.")
    result = call_tool(payload["name"], payload.get("arguments", {}))
    return respond(result, status=200 if result.get("ok") else 400)


@require_GET
@api_access
def service_list(request):
    query = {key: request.GET[key] for key in ["query", "category"] if key in request.GET}
    for key in ["offset", "limit"]:
        if key in request.GET:
            try:
                query[key] = int(request.GET[key])
            except ValueError as exc:
                raise PishkhanError("INVALID_PAGINATION", "offset/limit must be integers.") from exc
    result = call_tool("p24_list_services", query)
    return respond(result, status=200 if result.get("ok") else 400)


@require_GET
@api_access
def action_list(request):
    query = {key: request.GET[key] for key in ["query", "service_id"] if key in request.GET}
    for key in ["offset", "limit"]:
        if key in request.GET:
            try:
                query[key] = int(request.GET[key])
            except ValueError as exc:
                raise PishkhanError("INVALID_PAGINATION", "offset/limit must be integers.") from exc
    result = call_tool("p24_search_actions", query)
    return respond(result, status=200 if result.get("ok") else 400)


@require_GET
@api_access
def operation_list(request):
    session = get_session(request.GET.get("session_id", ""))
    return respond(
        {
            "ok": True,
            "items": [item.public_dict() for item in session.operations.select_related("session")[:50]],
        }
    )


@csrf_exempt
@require_POST
@api_access
def chat(request):
    from apps.agent.runner import run_turn

    payload = body(request)
    if not isinstance(payload.get("message"), str) or not payload["message"].strip():
        raise PishkhanError("MESSAGE_REQUIRED", "متن درخواست لازم است.")
    if not isinstance(payload.get("session_id"), str):
        raise PishkhanError("SESSION_REQUIRED", "ابتدا نشست ایجاد کنید.")
    conversation_id = payload.get("conversation_id")
    if conversation_id is not None and (not isinstance(conversation_id, str) or not conversation_id.strip()):
        raise PishkhanError("INVALID_CONVERSATION", "conversation_id باید رشتهٔ غیرخالی یا null باشد.")
    result = run_turn(
        session_id=payload["session_id"],
        message=payload["message"],
        conversation_id=payload.get("conversation_id"),
    )
    return respond(result, status=200 if result.get("ok") else 400)


@require_GET
def payment_return(request):
    return render(request, "payment_return.html")


@require_GET
@api_access
def conversations(request):
    from apps.core.models import Conversation

    session = get_session(request.GET.get("session_id", ""))
    rows = Conversation.objects.filter(session=session).order_by("-updated_at", "-id")[:30]
    return respond(
        {
            "ok": True,
            "items": [
                {
                    "conversation_id": str(row.pk),
                    "updated_at": row.updated_at.isoformat(),
                    "message_count": len(row.messages),
                    "preview": next(
                        (
                            str(m.get("content") or "")[:120]
                            for m in reversed(row.messages)
                            if m.get("role") == "user"
                        ),
                        "",
                    ),
                }
                for row in rows
            ],
        }
    )


@require_GET
@api_access
def conversation_history(request, conversation_id):
    from apps.agent.redaction import redact
    from apps.core.models import Conversation

    session = get_session(request.GET.get("session_id", ""))
    row = Conversation.objects.filter(session=session, pk=conversation_id).first()
    if row is None:
        return respond({"ok": False, "error": {"code": "conversation_not_found"}}, status=404)
    messages = [
        {"role": m["role"], "content": m.get("content") or ""}
        for m in row.messages
        if m.get("role") in {"user", "assistant"} and m.get("content")
    ]
    return respond({"ok": True, "conversation_id": str(row.pk), "messages": redact(messages)})
