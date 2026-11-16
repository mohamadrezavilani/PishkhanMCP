"""Protocol-level checks through the official SDK's HTTP and stdio transports."""

import asyncio
import json
import os
import sys

import pytest
from django.conf import settings
from mcp import Client, StdioServerParameters
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from apps.mcpserver import server

HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}


@pytest.fixture
def example_registry(monkeypatch):
    calls = []

    def definitions():
        return [
            {
                "name": "p24_test_echo",
                "description": "Echo a string to verify MCP input and output handling.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True},
            }
        ]

    def call_tool(name, arguments):
        calls.append((name, arguments))
        return {"ok": True, "mode": "demo", "message": arguments["message"]}

    monkeypatch.setattr(server, "_list_tool_definitions", definitions)
    monkeypatch.setattr(server, "_execute_tool", call_tool)
    return calls


def rpc(client, method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = client.post("/mcp", json=payload, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    return body["result"]


def test_http_initialize_list_call_and_django_fallback(example_registry):
    async def fallback(scope, receive, send):
        await JSONResponse({"route": "django"})(scope, receive, send)

    with TestClient(server.build_mcp_app(fallback)) as client:
        initialized = rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pishkhan-test", "version": "1"},
            },
        )
        assert initialized["serverInfo"]["name"] == "PishkhanMCP"
        assert initialized["protocolVersion"] == "2025-11-25"
        assert "tools" in initialized["capabilities"]

        notification = client.post(
            "/mcp",
            headers=HEADERS,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
        )
        assert notification.status_code == 202

        listing = rpc(client, "tools/list", request_id=2)
        assert listing["tools"][0]["name"] == "p24_test_echo"
        assert listing["tools"][0]["inputSchema"]["required"] == ["message"]

        called = rpc(
            client,
            "tools/call",
            {
                "name": "p24_test_echo",
                "arguments": {"message": "سلام پیشخوان"},
            },
            request_id=3,
        )
        assert called["isError"] is False
        assert called["structuredContent"]["message"] == "سلام پیشخوان"
        assert json.loads(called["content"][0]["text"]) == called["structuredContent"]
        assert example_registry == [("p24_test_echo", {"message": "سلام پیشخوان"})]
        assert client.get("/health/").json() == {"route": "django"}


def test_http_rejects_invalid_arguments_before_dispatch(example_registry):
    with TestClient(server.build_mcp_app()) as client:
        result = rpc(
            client,
            "tools/call",
            {
                "name": "p24_test_echo",
                "arguments": {"message": 1234},
            },
        )
        assert result["isError"] is True
        assert result["structuredContent"]["error"]["code"] == "invalid_arguments"
        assert "1234" not in result["content"][0]["text"]
        unknown = rpc(client, "tools/call", {"name": "unknown", "arguments": {}}, request_id=2)
        assert unknown["isError"] is True
        assert unknown["structuredContent"]["error"]["code"] == "unknown_tool"
        assert not example_registry


def test_optional_shared_access_key_guards_mcp(example_registry, settings):
    settings.P24_ACCESS_KEY = "transport-test-key"
    with TestClient(server.build_mcp_app()) as client:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert client.post("/mcp", json=payload, headers=HEADERS).status_code == 401
        response = client.post(
            "/mcp",
            json=payload,
            headers={**HEADERS, "Authorization": "Bearer transport-test-key"},
        )
        assert response.status_code == 200
        assert response.json()["result"]["tools"][0]["name"] == "p24_test_echo"


def test_modern_sdk_discovery_tools_resources_and_prompt(example_registry):
    async def check():
        async with Client(server.build_server(), mode="2026-07-28") as client:
            assert client.protocol_version == "2026-07-28"
            result = await client.call_tool("p24_test_echo", {"message": "hello"})
            assert not result.is_error
            assert result.structured_content["message"] == "hello"
            resources = await client.list_resources()
            assert {item.uri for item in resources.resources} == {server.GUIDE_URI, server.TOOLS_URI}
            guide = await client.read_resource(server.GUIDE_URI)
            assert "demo" in guide.contents[0].text
            prompt = await client.get_prompt("pishkhan_task", {"request": "قبض برق را بررسی کن"})
            assert "قبض برق" in prompt.messages[0].content.text

    asyncio.run(check())


def test_stdio_command_exposes_real_catalog():
    """Launch the management command exactly as a desktop MCP host would."""

    async def check():
        env = {**os.environ, "P24_MODE": "demo", "DB_HOST": "", "PYTHONUNBUFFERED": "1"}
        transport = StdioServerParameters(
            command=sys.executable,
            args=[str(settings.BASE_DIR / "manage.py"), "mcp_stdio"],
            cwd=str(settings.BASE_DIR),
            env=env,
        )
        async with Client(transport, mode="legacy", read_timeout_seconds=20) as client:
            assert client.server_info.name == "PishkhanMCP"
            listing = await client.list_tools()
            assert "p24_list_services" in {item.name for item in listing.tools}
            result = await client.call_tool("p24_list_services", {})
            assert not result.is_error
            assert isinstance(result.structured_content, dict)
            assert result.structured_content

    asyncio.run(check())
