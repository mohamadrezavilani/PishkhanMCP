"""HTTP contract and real demo flows through the Django API."""

import json
from unittest.mock import Mock

import pytest

from apps.core.models import AccountSession, Operation
from apps.core.tools import call_tool


@pytest.fixture(autouse=True)
def demo_settings(settings):
    settings.P24_MODE = "demo"
    settings.P24_ACCESS_KEY = ""
    settings.AGENT_BASE_URL = ""
    settings.AGENT_MODEL = ""


@pytest.fixture
def account(db):
    result = call_tool("p24_create_session", {})
    return AccountSession.objects.get(pk=result["session_id"])


def post_tool(client, name, arguments=None, **headers):
    return client.post(
        "/api/tools/call/",
        data=json.dumps({"name": name, "arguments": arguments or {}}),
        content_type="application/json",
        **headers,
    )


def test_health_and_tool_discovery_are_available(client):
    health = client.get("/health/")
    assert health.status_code == 200
    assert health.json()["ok"] and health.json()["mode"] == "demo"
    response = client.get("/api/tools/")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert "p24_capabilities" in {tool["name"] for tool in tools}
    assert all("inputSchema" in tool and "annotations" in tool for tool in tools)


def test_optional_access_key_applies_to_api_not_health(client, settings):
    settings.P24_ACCESS_KEY = "local-test-access-key"
    assert client.get("/api/tools/").status_code == 401
    assert client.get("/api/tools/", HTTP_AUTHORIZATION="Bearer wrong-key").status_code == 401
    assert client.get("/api/tools/", HTTP_AUTHORIZATION="Bearer local-test-access-key").status_code == 200
    assert post_tool(client, "p24_capabilities").status_code == 401
    assert (
        post_tool(client, "p24_capabilities", HTTP_AUTHORIZATION="Bearer local-test-access-key").status_code
        == 200
    )
    assert client.get("/health/").status_code == 200


def test_service_and_action_pagination(client):
    services = client.get("/api/services/?category=postal&offset=1&limit=2")
    assert services.status_code == 200
    data = services.json()
    assert data["ok"] and data["total"] == 4
    assert len(data["items"]) == 2 and data["offset"] == 1 and data["next_offset"] == 3
    assert all("input_schema" not in item for item in data["items"])
    first = client.get("/api/actions/?offset=0&limit=3")
    second = client.get("/api/actions/?offset=3&limit=3")
    assert first.status_code == second.status_code == 200
    assert len(first.json()["items"]) == len(second.json()["items"]) == 3
    assert first.json()["next_offset"] == 3
    assert not (
        {item["id"] for item in first.json()["items"]} & {item["id"] for item in second.json()["items"]}
    )


@pytest.mark.parametrize(
    "path", ["/api/services/?offset=oops", "/api/services/?limit=0", "/api/actions/?limit=0"]
)
def test_invalid_pagination_is_structured(client, path):
    response = client.get(path)
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"]


@pytest.mark.parametrize(
    "payload", ["[invalid", "[]", '{"name":123}', '{"name":"p24_capabilities","arguments":[]}']
)
def test_invalid_json_and_tool_call_shape_return_400(client, payload):
    response = client.post("/api/tools/call/", data=payload, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_session_inquiry_status_and_receipt_flow_through_http(client, db):
    created = post_tool(client, "p24_create_session")
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    inquiry = post_tool(
        client,
        "p24_electricity_bill",
        {
            "session_id": session_id,
            "bill_id": "00012345",
            "idempotency_key": "api-bill",
        },
    )
    assert inquiry.status_code == 200
    operation_id = inquiry.json()["operation_id"]
    assert inquiry.json()["result"]["demo"]
    status = post_tool(
        client, "p24_operation_status", {"session_id": session_id, "operation_id": operation_id}
    )
    assert status.status_code == 200 and status.json()["status"] == "completed"
    receipts = post_tool(client, "p24_get_receipt", {"session_id": session_id, "operation_id": operation_id})
    assert receipts.status_code == 200 and receipts.json()["receipt_available"] is False
    history = client.get("/api/operations/", {"session_id": session_id})
    assert history.status_code == 200
    assert [item["operation_id"] for item in history.json()["items"]] == [operation_id]


def test_http_replay_and_session_boundaries(account, client):
    arguments = {"session_id": str(account.pk), "plate": "12الف34567", "idempotency_key": "http-toll"}
    first = post_tool(client, "p24_toll_summary", arguments)
    replay = post_tool(client, "p24_toll_summary", arguments)
    assert first.status_code == replay.status_code == 200
    assert first.json()["operation_id"] == replay.json()["operation_id"]
    assert Operation.objects.filter(session=account).count() == 1
    other = AccountSession.objects.create(mode="demo")
    denied = post_tool(
        client,
        "p24_operation_status",
        {
            "session_id": str(other.pk),
            "operation_id": first.json()["operation_id"],
        },
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "OPERATION_NOT_FOUND"
    assert client.get("/api/operations/", {"session_id": str(other.pk)}).json()["items"] == []


def test_chat_reports_missing_configuration(account, client):
    response = client.post(
        "/api/chat/",
        data=json.dumps({"session_id": str(account.pk), "message": "خدمات را نشان بده"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "agent_not_configured"


@pytest.mark.parametrize("message", ["", "   ", 123, None])
def test_chat_rejects_invalid_message_before_model_call(account, client, message):
    response = client.post(
        "/api/chat/",
        data=json.dumps({"session_id": str(account.pk), "message": message}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MESSAGE_REQUIRED"


def test_chat_rejects_object_conversation_identifier(account, client, settings):
    settings.AGENT_BASE_URL = "https://model.example/v1"
    settings.AGENT_MODEL = "test-model"
    response = client.post(
        "/api/chat/",
        data=json.dumps(
            {
                "session_id": str(account.pk),
                "message": "ادامه بده",
                "conversation_id": {"id": "invalid"},
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_executor_failure_has_json_unknown_operation_not_http_500(account, client, monkeypatch):
    monkeypatch.setattr("apps.providers.demo.inquiry", Mock(side_effect=RuntimeError("simulated-crash")))
    response = post_tool(
        client,
        "p24_electricity_bill",
        {
            "session_id": str(account.pk),
            "bill_id": "12345",
            "idempotency_key": "api-crash",
        },
    )
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["status"] == "unknown"
    assert response.json()["operation_id"]


def test_method_contracts(client):
    assert client.get("/api/tools/call/").status_code == 405
    assert client.post("/api/tools/").status_code == 405
