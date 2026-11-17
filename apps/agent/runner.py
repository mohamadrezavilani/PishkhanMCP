"""Bounded OpenAI-compatible model/tool loop over the actual core tool registry."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils import timezone
from jsonschema import Draft202012Validator

from apps.core.models import AccountSession, AgentDailyUsage, Conversation

from .prompts import system_prompt
from .redaction import collect_secrets, redact

_SESSION_CREATORS = {"p24_create_session", "p24_new_session", "p24_session_create"}


def _list_tools() -> list[dict[str, Any]]:
    from apps.core.tools import list_tools

    return list_tools()


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from apps.core.tools import call_tool

    return call_tool(name, arguments)


def _make_client() -> httpx.Client:
    headers = {"Content-Type": "application/json"}
    if settings.AGENT_API_KEY:
        headers["Authorization"] = f"Bearer {settings.AGENT_API_KEY}"
    if settings.AGENT_WORKSPACE_ID:
        headers["anthropic-workspace-id"] = settings.AGENT_WORKSPACE_ID
    proxy = settings.AGENT_PROXY_URL or None
    return httpx.Client(
        timeout=settings.AGENT_TIMEOUT, headers=headers, proxy=proxy, trust_env=not bool(proxy)
    )


def _error(code: str, message: str, *, retryable: bool = False, **details: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "retryable": retryable, "details": details},
    }


def _model_tools(registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for name, tool in registry.items():
        schema = deepcopy(tool["inputSchema"])
        schema.pop("$schema", None)
        properties = schema.setdefault("properties", {})
        properties.pop("session_id", None)
        properties.pop("idempotency_key", None)
        if "required" in schema:
            schema["required"] = [
                key for key in schema["required"] if key not in {"session_id", "idempotency_key"}
            ]
        result.append(
            {
                "type": "function",
                "function": {"name": name, "description": tool.get("description", ""), "parameters": schema},
            }
        )
    return result


def _assistant_message(payload: Any) -> dict[str, Any]:
    """Retain only Chat Completions assistant fields, never model-supplied roles."""
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Model response has no assistant message") from exc
    if not isinstance(message, dict):
        raise ValueError("Assistant message is not an object")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise ValueError("Only text assistant content is supported")
    normalized: dict[str, Any] = {"role": "assistant", "content": content}
    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        raise ValueError("tool_calls must be an array")
    if tool_calls:
        normalized["tool_calls"] = []
        for item in tool_calls:
            if not isinstance(item, dict) or not isinstance(item.get("function"), dict):
                raise ValueError("Invalid tool call")
            function = item["function"]
            if not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("Tool call needs an ID")
            if not isinstance(function.get("name"), str) or not isinstance(function.get("arguments"), str):
                raise ValueError("Tool call needs a function name and JSON arguments")
            normalized["tool_calls"].append(
                {
                    "id": item["id"],
                    "type": "function",
                    "function": {"name": function["name"], "arguments": function["arguments"]},
                }
            )
    return normalized


def _idempotency_key(conversation_id: str, turn_id: str, call_id: str, name: str) -> str:
    value = f"{conversation_id}:{turn_id}:{call_id}:{name}".encode()
    return "agent-" + sha256(value).hexdigest()


def _execute_tool(
    call: dict[str, Any],
    *,
    registry: dict[str, dict[str, Any]],
    session_id: str,
    conversation_id: str,
    turn_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    name = call["function"]["name"]
    try:
        arguments = json.loads(call["function"]["arguments"])
    except (ValueError, TypeError):
        return {}, _error("invalid_tool_arguments", "ورودی ابزار باید یک شیء JSON معتبر باشد.")
    if not isinstance(arguments, dict):
        return {}, _error("invalid_tool_arguments", "ورودی ابزار باید یک شیء JSON باشد.")
    if name not in registry:
        return arguments, _error("unknown_tool", "این ابزار در اتصال جاری ارائه نشده است.", tool=name)
    supplied_session = arguments.pop("session_id", None)
    if supplied_session is not None and str(supplied_session) != session_id:
        return arguments, _error("session_mismatch", "ابزار فقط می‌تواند از حساب همین گفت‌وگو استفاده کند.")
    schema = registry[name]["inputSchema"]
    properties = schema.get("properties", {})
    if "session_id" in properties:
        arguments["session_id"] = session_id
    if "idempotency_key" in properties and not arguments.get("idempotency_key"):
        arguments["idempotency_key"] = _idempotency_key(conversation_id, turn_id, call["id"], name)
    errors = list(Draft202012Validator(schema).iter_errors(arguments))
    if errors:
        return arguments, _error(
            "invalid_tool_arguments",
            "ورودی ابزار با قرارداد آن سازگار نیست؛ فیلدهای لازم را اصلاح کنید.",
            validation=[{"path": list(error.absolute_path), "rule": error.validator} for error in errors[:5]],
        )
    try:
        result = _call_tool(name, arguments)
    except Exception:
        # Provider/core errors normally already return structured error objects.
        # Unexpected exception text can contain credentials or entire requests.
        result = _error(
            "tool_execution_error", "اجرای ابزار با خطای داخلی مواجه شد؛ وضعیت عملیات را بررسی کنید."
        )
    if not isinstance(result, dict):
        result = _error("invalid_tool_result", "ابزار پاسخ ساختاریافته معتبر برنگرداند.")
    return arguments, result


def _save_history(conversation: Conversation, messages: list[dict[str, Any]], secrets: set[str]) -> bool:
    """Atomically replace the history only if its loaded snapshot is still current.

    Wall-clock timestamps can repeat or move backwards, so updated_at is only
    metadata, never a concurrency token. The revision catches same-content writes;
    the messages predicate also protects against legacy/admin writers that do not
    increment it. All application history writers should use this helper.
    Already-issued tools are not rolled back or automatically replayed on conflict.
    """
    saved_messages = redact(messages, secrets)
    saved_at = timezone.now()
    changed = Conversation.objects.filter(
        pk=conversation.pk,
        history_version=conversation.history_version,
        messages=conversation.messages,
    ).update(
        messages=saved_messages,
        history_version=F("history_version") + 1,
        updated_at=saved_at,
    )
    if changed:
        conversation.messages = saved_messages
        conversation.history_version += 1
        conversation.updated_at = saved_at
    return bool(changed)


def _reserve_daily_message() -> dict[str, Any] | None:
    """Reserve one user chat turn against the deployment-wide daily budget."""
    limit = settings.AGENT_DAILY_MESSAGE_LIMIT
    if not isinstance(limit, int) or not 1 <= limit <= 1000:
        return {"error": "invalid_limit"}
    today = timezone.localdate()
    usage, _ = AgentDailyUsage.objects.get_or_create(usage_date=today)
    reserved = AgentDailyUsage.objects.filter(pk=usage.pk, messages_used__lt=limit).update(
        messages_used=F("messages_used") + 1, updated_at=timezone.now()
    )
    usage.refresh_from_db()
    if not reserved:
        return {
            "error": "daily_limit",
            "limit": limit,
            "used": usage.messages_used,
            "remaining": 0,
            "resets_on": (today + timezone.timedelta(days=1)).isoformat(),
        }
    return {
        "limit": limit,
        "used": usage.messages_used,
        "remaining": max(0, limit - usage.messages_used),
        "resets_on": (today + timezone.timedelta(days=1)).isoformat(),
    }


def run_turn(
    session_id: str,
    message: str,
    conversation_id: str | None = None,
    *,
    tool_names: frozenset[str] | None = None,
    extra_instructions: str = "",
) -> dict[str, Any]:
    """Execute one user turn and return reply, trace, and continuation identifier.

    The same domain tools are used by MCP, REST, and this agent. No keyword or
    fabricated-result fallback is used when a model has not been configured.
    """
    if not isinstance(message, str) or not message.strip():
        return _error("invalid_message", "متن پیام نمی‌تواند خالی باشد.")
    try:
        session = AccountSession.objects.get(pk=session_id)
    except (AccountSession.DoesNotExist, ValidationError, ValueError, TypeError):
        return _error("session_not_found", "ابتدا یک جلسه معتبر ایجاد کنید.")
    if session.state == "closed":
        return _error("session_closed", "نشست بسته شده است؛ پیش از ادامه یک نشست تازه ایجاد کنید.")
    session_id = str(session.pk)
    base_url = settings.AGENT_BASE_URL.rstrip("/")
    missing = [name for name in ("AGENT_BASE_URL", "AGENT_MODEL") if not getattr(settings, name, "")]
    if missing:
        return _error(
            "agent_not_configured",
            "مدل ایجنت تنظیم نشده است؛ آدرس سرویس و نام مدل را تنظیم کنید.",
            missing_settings=missing,
        )
    if urlsplit(base_url).scheme not in {"http", "https"} or not urlsplit(base_url).netloc:
        return _error("agent_not_configured", "AGENT_BASE_URL باید یک آدرس معتبر http یا https باشد.")
    max_steps = settings.AGENT_MAX_STEPS
    if not isinstance(max_steps, int) or not 1 <= max_steps <= 50:
        return _error("agent_not_configured", "AGENT_MAX_STEPS باید بین ۱ و ۵۰ باشد.")
    if conversation_id:
        try:
            conversation = Conversation.objects.get(pk=conversation_id, session=session)
        except (Conversation.DoesNotExist, ValidationError, ValueError, TypeError):
            return _error("conversation_not_found", "گفت‌وگو برای حساب جاری یافت نشد.")
    else:
        conversation = Conversation.objects.create(session=session)

    usage = _reserve_daily_message()
    if usage and usage.get("error") == "daily_limit":
        return _error(
            "agent_daily_limit",
            "سقف روزانهٔ پیام‌های ایجنت تمام شده است؛ فردا دوباره تلاش کنید.",
            limit=usage["limit"],
            used=usage["used"],
            remaining=0,
            resets_on=usage["resets_on"],
        )
    if usage and usage.get("error"):
        return _error("agent_budget_configuration", "تنظیم سقف مصرف روزانه معتبر نیست.")

    registry = {
        tool["name"]: tool
        for tool in _list_tools()
        if tool["name"] not in _SESSION_CREATORS and (tool_names is None or tool["name"] in tool_names)
    }
    history = deepcopy(conversation.messages)
    history.append({"role": "user", "content": message})
    secrets = collect_secrets(history)
    model_messages = [
        {
            "role": "system",
            "content": system_prompt(mode=session.mode, account_state=session.state)
            + "\n"
            + extra_instructions,
        }
    ]
    model_messages.extend(history)
    model_tools = _model_tools(registry)
    trace: list[dict[str, Any]] = []
    cache: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {}
    turn_id = str(uuid.uuid4())
    failure: dict[str, Any] | None = None
    reply = ""
    steps = 0
    max_calls = max_steps * 4
    with _make_client() as client:
        for step_number in range(1, max_steps + 1):
            steps = step_number
            request = {
                "model": settings.AGENT_MODEL,
                "messages": model_messages,
                "max_tokens": settings.AGENT_MAX_OUTPUT_TOKENS,
            }
            if model_tools:
                request.update({"tools": model_tools, "tool_choice": "auto"})
            try:
                response = client.post(f"{base_url}/chat/completions", json=request)
                response.raise_for_status()
                assistant = _assistant_message(response.json())
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                failure = _error(
                    "model_http_error",
                    "سرویس مدل درخواست را نپذیرفت؛ تنظیمات مدل و وضعیت ارائه‌دهنده را بررسی کنید.",
                    retryable=status == 429 or status >= 500,
                    status_code=status,
                )
                break
            except httpx.RequestError:
                failure = _error("model_connection_error", "ارتباط با سرویس مدل برقرار نشد.", retryable=True)
                break
            except (ValueError, TypeError):
                failure = _error(
                    "invalid_model_response", "پاسخ مدل با قرارداد Chat Completions سازگار نبود."
                )
                break
            history.append(assistant)
            model_messages.append(assistant)
            calls = assistant.get("tool_calls", [])
            if not calls:
                reply = assistant.get("content") or ""
                if not reply.strip():
                    failure = _error("empty_model_reply", "مدل پاسخ متنی یا فراخوانی ابزار ارائه نکرد.")
                break
            for call in calls:
                name = call["function"]["name"]
                signature = name + "\n" + call["function"]["arguments"]
                reused = call["id"] in cache
                if reused:
                    previous_signature, arguments, result = cache[call["id"]]
                    if previous_signature != signature:
                        arguments = {}
                        result = _error(
                            "tool_call_id_reused", "شناسه فراخوانی ابزار با درخواست متفاوت تکرار شده است."
                        )
                elif len(trace) >= max_calls:
                    arguments = {}
                    result = _error("agent_tool_limit", "حداکثر تعداد فراخوانی ابزار در این نوبت رسیده است.")
                    failure = result
                else:
                    arguments, result = _execute_tool(
                        call,
                        registry=registry,
                        session_id=session_id,
                        conversation_id=str(conversation.pk),
                        turn_id=turn_id,
                    )
                    cache[call["id"]] = (signature, arguments, result)
                secrets.update(collect_secrets(arguments))
                secrets.update(collect_secrets(result))
                # Tokens returned by login remain with the domain session; model
                # does not need to receive or echo them to make subsequent calls.
                public_result = redact(result, secrets)
                tool_message = {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(public_result, ensure_ascii=False, default=str),
                }
                history.append(tool_message)
                model_messages.append(tool_message)
                trace.append(
                    {
                        "id": call["id"],
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                        "reused": reused,
                    }
                )
            if failure:
                break
        else:
            failure = _error(
                "agent_step_limit",
                "تعداد مراحل این نوبت به سقف رسید؛ عملیات موجود را با شناسه آن پیگیری کنید.",
            )

    progress = {"request_ids": [], "operation_ids": [], "quote_ids": [], "last_tool_error": None}
    for entry in trace:
        value = entry.get("result", {})
        inner = value.get("result", {}) if isinstance(value.get("result"), dict) else {}
        for field, plural in (
            ("request_id", "request_ids"),
            ("operation_id", "operation_ids"),
            ("quote_id", "quote_ids"),
        ):
            identifier = value.get(field) or inner.get(field)
            if identifier and identifier not in progress[plural]:
                progress[plural].append(identifier)
        error = value.get("error") or inner.get("error")
        progress["last_tool_error"] = {"tool": entry["name"], "error": error} if error else None
    if failure and failure["error"]["code"] == "agent_step_limit":
        failure["error"]["details"]["progress"] = progress
        last = progress["last_tool_error"]
        if last:
            failure["error"]["message"] += (
                " \u062e\u0637\u0627\u06cc \u0622\u062e\u0631 \u0627\u0628\u0632\u0627\u0631: "
                + str(last["error"].get("code", "unknown"))
            )
    secrets.update(collect_secrets(history))
    if failure:
        reply = failure["error"]["message"]
        history.append({"role": "assistant", "content": reply})
    if not _save_history(conversation, history, secrets):
        failure = _error(
            "conversation_conflict",
            "گفت‌وگو هم‌زمان تغییر کرده است؛ نتیجه ابزارهای این نوبت را از شناسه‌های پیگیری بررسی کنید.",
        )
        reply = failure["error"]["message"]
    result = {
        "ok": failure is None,
        "session_id": session_id,
        "conversation_id": str(conversation.pk),
        "mode": session.mode,
        "reply": redact(reply, secrets),
        "tool_calls": redact(trace, secrets),
        "steps": steps,
        "stop_reason": failure["error"]["code"] if failure else "completed",
        "agent_usage": usage,
        "progress": redact(progress, secrets),
    }
    if failure:
        result["error"] = failure["error"]
    return result
