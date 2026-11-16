import json
import uuid
from unittest.mock import Mock

import httpx
import pytest
from django.utils import timezone

from apps.agent import runner
from apps.core.models import AccountSession, Conversation, Operation

TOOLS = [
    {
        "name": "p24_lookup",
        "description": "Find a service",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}, "service_id": {"type": "string"}},
            "required": ["session_id", "service_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "p24_execute_action",
        "description": "Execute a configured action",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "action_id": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "parameters": {"type": "object"},
            },
            "required": ["session_id", "action_id", "idempotency_key"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "p24_verify_otp",
        "description": "Verify a supplied OTP",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}, "otp": {"type": "string"}},
            "required": ["session_id", "otp"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "p24_create_session",
        "description": "Create another session",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def tool_call(name, arguments, call_id="call-1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def response(content=None, calls=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {"choices": [{"message": message}]}


@pytest.fixture
def account(db):
    return AccountSession.objects.create(mode="demo")


@pytest.fixture
def model(settings, monkeypatch):
    settings.AGENT_BASE_URL = "https://model.example/v1"
    settings.AGENT_MODEL = "test-tool-model"
    settings.AGENT_API_KEY = "test-model-key"
    settings.AGENT_MAX_STEPS = 5
    settings.AGENT_TIMEOUT = 10
    monkeypatch.setattr(runner, "_list_tools", lambda: TOOLS)
    tool = Mock(
        return_value={"ok": True, "operation_id": "operation-1", "status": "completed", "mode": "demo"}
    )
    monkeypatch.setattr(runner, "_call_tool", tool)
    requests = []

    def configure(responses):
        remaining = iter(responses)

        def handler(request):
            requests.append(json.loads(request.content))
            item = next(remaining)
            if callable(item):
                return item(request)
            if isinstance(item, httpx.Response):
                return item
            return httpx.Response(200, json=item)

        monkeypatch.setattr(
            runner, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
        )

    return configure, requests, tool


def test_unconfigured_agent_does_not_fabricate_reply(account, settings, monkeypatch):
    settings.AGENT_BASE_URL = ""
    settings.AGENT_MODEL = ""
    client = Mock()
    monkeypatch.setattr(runner, "_make_client", client)
    result = runner.run_turn(str(account.pk), "قبض را پرداخت کن")
    assert result["error"]["code"] == "agent_not_configured"
    assert result["error"]["details"]["missing_settings"] == ["AGENT_BASE_URL", "AGENT_MODEL"]
    assert not Conversation.objects.exists()
    client.assert_not_called()


def test_actual_multistep_loop_preserves_order_and_binds_account(account, model):
    configure, requests, tool = model
    configure(
        [
            response(calls=[tool_call("p24_lookup", {"service_id": "electricity"}, "lookup")]),
            response(calls=[tool_call("p24_execute_action", {"action_id": "electricity.lookup"}, "execute")]),
            response("استعلام آزمایشی تکمیل شد."),
        ]
    )
    result = runner.run_turn(str(account.pk), "قبض برق را در حالت آزمایشی بررسی کن")
    assert result["ok"]
    assert result["steps"] == 3
    assert result["mode"] == "demo"
    assert tool.call_count == 2
    assert [call.args[0] for call in tool.call_args_list] == ["p24_lookup", "p24_execute_action"]
    assert all(call.args[1]["session_id"] == str(account.pk) for call in tool.call_args_list)
    key = tool.call_args_list[1].args[1]["idempotency_key"]
    assert key.startswith("agent-") and len(key) == 70
    assert [msg["role"] for msg in requests[2]["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]
    advertised = {item["function"]["name"]: item["function"] for item in requests[0]["tools"]}
    assert "p24_create_session" not in advertised
    assert "session_id" not in advertised["p24_lookup"]["parameters"]["properties"]
    assert "idempotency_key" not in advertised["p24_execute_action"]["parameters"]["properties"]
    conversation = Conversation.objects.get(pk=result["conversation_id"])
    assert conversation.session_id == account.pk
    assert conversation.messages[-1]["content"] == result["reply"]


def test_unknown_tool_is_returned_as_error_without_execution(account, model):
    configure, requests, tool = model
    configure([response(calls=[tool_call("invented_tool", {})]), response("ابزار در این اتصال موجود نیست.")])
    result = runner.run_turn(str(account.pk), "خدمت را بررسی کن")
    assert result["ok"]
    tool.assert_not_called()
    assert json.loads(requests[1]["messages"][-1]["content"])["error"]["code"] == "unknown_tool"


def test_model_cannot_switch_sessions(account, model):
    configure, requests, tool = model
    configure(
        [
            response(
                calls=[
                    tool_call("p24_lookup", {"service_id": "electricity", "session_id": str(uuid.uuid4())})
                ]
            ),
            response("باید از حساب جاری استفاده شود."),
        ]
    )
    result = runner.run_turn(str(account.pk), "قبض برق را بررسی کن")
    assert result["ok"]
    tool.assert_not_called()
    assert json.loads(requests[1]["messages"][-1]["content"])["error"]["code"] == "session_mismatch"


def test_conversation_belongs_to_one_account(account, model):
    other = AccountSession.objects.create(mode="demo")
    conversation = Conversation.objects.create(session=other)
    result = runner.run_turn(str(account.pk), "ادامه بده", str(conversation.pk))
    assert result["error"]["code"] == "conversation_not_found"


def test_closed_session_does_not_contact_model(account, model, monkeypatch):
    account.state = "closed"
    account.save(update_fields=["state"])
    client = Mock()
    monkeypatch.setattr(runner, "_make_client", client)
    result = runner.run_turn(str(account.pk), "ادامه بده")
    assert result["error"]["code"] == "session_closed"
    assert not Conversation.objects.filter(session=account).exists()
    client.assert_not_called()


def test_step_limit_keeps_executed_operation_trace(account, model, settings):
    configure, _, tool = model
    settings.AGENT_MAX_STEPS = 1
    configure([response(calls=[tool_call("p24_execute_action", {"action_id": "parcel.lookup"})])])
    result = runner.run_turn(str(account.pk), "استعلام آزمایشی را انجام بده")
    assert not result["ok"]
    assert result["stop_reason"] == "agent_step_limit"
    assert result["tool_calls"][0]["result"]["operation_id"] == "operation-1"
    assert tool.call_count == 1
    history = Conversation.objects.get(pk=result["conversation_id"]).messages
    assert history[-2]["role"] == "tool"


def test_duplicate_call_id_does_not_repeat_operation(account, model):
    configure, _, tool = model
    call = tool_call("p24_execute_action", {"action_id": "parcel.lookup"}, "same-call")
    configure([response(calls=[call]), response(calls=[call]), response("نتیجه آزمایشی آماده است.")])
    result = runner.run_turn(str(account.pk), "استعلام آزمایشی را انجام بده")
    assert result["ok"]
    assert tool.call_count == 1
    assert result["tool_calls"][1]["reused"]
    assert (
        result["tool_calls"][0]["arguments"]["idempotency_key"]
        == result["tool_calls"][1]["arguments"]["idempotency_key"]
    )


def test_malformed_arguments_and_missing_inputs_do_not_execute(account, model):
    configure, requests, tool = model
    broken = tool_call("p24_lookup", {})
    broken["function"]["arguments"] = "[invalid"
    configure(
        [
            response(calls=[broken]),
            response(calls=[tool_call("p24_lookup", {}, "missing-input")]),
            response("شناسه خدمت را مشخص کنید."),
        ]
    )
    result = runner.run_turn(str(account.pk), "بررسی کن")
    assert result["ok"]
    tool.assert_not_called()
    assert json.loads(requests[1]["messages"][-1]["content"])["error"]["code"] == "invalid_tool_arguments"
    assert json.loads(requests[2]["messages"][-1]["content"])["error"]["code"] == "invalid_tool_arguments"


def test_otp_is_used_then_removed_from_persisted_history_and_public_trace(account, model):
    configure, requests, tool = model
    tool.return_value = {"ok": True, "state": "authenticated", "access_token": "secret-access-token"}
    configure(
        [
            response(calls=[tool_call("p24_verify_otp", {"otp": "246810"})]),
            response("ورود آزمایشی با کد 246810 انجام شد."),
        ]
    )
    result = runner.run_turn(str(account.pk), "کد تایید: 246810")
    assert tool.call_args.args[1]["otp"] == "246810"
    persisted = json.dumps(
        Conversation.objects.get(pk=result["conversation_id"]).messages, ensure_ascii=False
    )
    public = json.dumps(result, ensure_ascii=False)
    assert "246810" not in persisted
    assert "secret-access-token" not in persisted
    assert "246810" not in public
    assert "secret-access-token" not in public
    assert "secret-access-token" not in requests[1]["messages"][-1]["content"]
    assert "[REDACTED]" in persisted


def test_model_failure_does_not_echo_remote_error_body(account, model):
    configure, _, tool = model
    configure([httpx.Response(401, json={"error": "bad key secret-provider-credential"})])
    result = runner.run_turn(str(account.pk), "خدمات را نشان بده")
    assert result["error"]["code"] == "model_http_error"
    assert result["error"]["details"]["status_code"] == 401
    assert "secret-provider-credential" not in json.dumps(result)
    tool.assert_not_called()


def test_continuation_preserves_previous_tool_message_pairs(account, model):
    configure, requests, _ = model
    configure(
        [
            response(calls=[tool_call("p24_lookup", {"service_id": "electricity"})]),
            response("اطلاعات آزمایشی قبض دریافت شد."),
            response("این ادامه همان گفت‌وگو است."),
        ]
    )
    first = runner.run_turn(str(account.pk), "قبض برق را بررسی کن")
    second = runner.run_turn(str(account.pk), "نتیجه را توضیح بده", first["conversation_id"])
    assert second["ok"]
    assert second["conversation_id"] == first["conversation_id"]
    assert [item["role"] for item in requests[2]["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]


def test_concurrent_history_update_is_not_silently_overwritten(account, model):
    configure, _, _ = model
    conversation = Conversation.objects.create(session=account)

    def concurrent_response(request):
        Conversation.objects.filter(pk=conversation.pk).update(
            messages=[{"role": "assistant", "content": "another completed turn"}], updated_at=timezone.now()
        )
        return httpx.Response(200, json=response("پاسخ نوبت جاری"))

    configure([concurrent_response])
    result = runner.run_turn(str(account.pk), "ادامه بده", str(conversation.pk))
    assert result["error"]["code"] == "conversation_conflict"
    conversation.refresh_from_db()
    assert conversation.messages[0]["content"] == "another completed turn"


def test_model_loop_executes_real_demo_tools_and_tracks_operation(account, model, monkeypatch):
    from apps.core.tools import call_tool, list_tools

    configure, _, _ = model
    monkeypatch.setattr(runner, "_list_tools", list_tools)
    monkeypatch.setattr(runner, "_call_tool", call_tool)

    def follow_operation(request):
        previous = json.loads(json.loads(request.content)["messages"][-1]["content"])
        assert previous["ok"]
        assert previous["result"]["demo"]
        return httpx.Response(
            200,
            json=response(
                calls=[
                    tool_call("p24_operation_status", {"operation_id": previous["operation_id"]}, "status")
                ]
            ),
        )

    configure(
        [
            response(calls=[tool_call("p24_toll_summary", {"plate": "۱۲الف۳۴۵۶۷"}, "toll")]),
            follow_operation,
            response("استعلام آزمایشی عوارض تکمیل شد؛ مبلغ، واقعی نیست."),
        ]
    )
    result = runner.run_turn(str(account.pk), "عوارض این پلاک را آزمایشی بررسی کن")
    assert result["ok"]
    assert result["steps"] == 3
    operation = Operation.objects.get(session=account)
    assert operation.service_id == "freeway"
    assert operation.status == "completed"
    assert operation.request_data["plate"] == "12الف34567"
    assert result["tool_calls"][1]["result"]["operation_id"] == str(operation.pk)
