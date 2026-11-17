"""Bridge the core tool registry to the official MCP Python SDK.

The SDK owns protocol negotiation, HTTP framing, and stdio framing. Business
logic remains in ``apps.core.tools`` and is shared with the Django API.
"""

from __future__ import annotations

import json
import logging
from hmac import compare_digest
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from jsonschema import Draft202012Validator
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    GetPromptRequestParams,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    Prompt,
    PromptArgument,
    PromptMessage,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

INSTRUCTIONS = """You are connected to Pishkhan MCP (پیشخوان).
Start with p24_list_services and inspect a service's requirements before execution.
Use the session_id returned by login for the same user's subsequent requests.
Request missing inputs from the user; never invent identifiers or credentials.
Follow the returned operation status and next action. A timeout is not proof of
failure, and a payment redirect is not proof of payment. Use status tools before
retrying an operation that may already have taken effect.
Keep demo and live results distinct: never present demonstration data as a real
inquiry, login, charge, or payment. Report an unavailable integration honestly.
Respond in the user's language; Persian is supported.
"""

GUIDE_URI = "pishkhan://guide"
TOOLS_URI = "pishkhan://tools"


class MCPAccessKeyMiddleware:
    """Optional shared development access key, independent of Pishkhan login."""

    def __init__(self, app: ASGIApp, access_key: str):
        self.app = app
        self.access_key = access_key.encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
            authorization = dict(scope.get("headers", [])).get(b"authorization", b"")
            scheme, _, credential = authorization.partition(b" ")
            if scheme.lower() != b"bearer" or not compare_digest(credential, self.access_key):
                await JSONResponse(
                    {"error": "unauthorized", "message": "A valid P24_ACCESS_KEY bearer token is required."},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="PishkhanMCP"'},
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _list_tool_definitions() -> list[dict[str, Any]]:
    # Import lazily: Django app loading and the stdio command must finish before
    # business modules that use the ORM are imported.
    from apps.core.tools import list_tools

    return list_tools()


def _execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from apps.core.tools import call_tool

    return call_tool(name, arguments)


def _result(payload: dict[str, Any], *, is_error: bool = False) -> CallToolResult:
    """Return both structured data and a JSON text fallback for older hosts."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structured_content=payload,
        is_error=is_error,
    )


def _error(code: str, message: str, **details: Any) -> CallToolResult:
    return _result(
        {"ok": False, "error": {"code": code, "message": message, **details}},
        is_error=True,
    )


async def _handle_list_tools(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListToolsResult:
    definitions = await sync_to_async(_list_tool_definitions, thread_sensitive=True)()
    return ListToolsResult(tools=[Tool.model_validate(item) for item in definitions])


async def _handle_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    definitions = await sync_to_async(_list_tool_definitions, thread_sensitive=True)()
    definition = next((item for item in definitions if item["name"] == params.name), None)
    if definition is None:
        return _error("unknown_tool", "Unknown tool. Use tools/list to discover available tools.")

    arguments = params.arguments or {}
    validator = Draft202012Validator(definition.get("inputSchema", {"type": "object"}))
    invalid = next(validator.iter_errors(arguments), None)
    if invalid is not None:
        # Validation messages can contain the rejected value (e.g. an OTP).
        # Return useful field information without echoing the input.
        field = ".".join(str(part) for part in invalid.absolute_path) or "$"
        return _error(
            "invalid_arguments",
            "Arguments do not match the tool's input schema.",
            field=field,
            rule=invalid.validator,
        )

    try:
        payload = await sync_to_async(_execute_tool, thread_sensitive=True)(params.name, arguments)
    except Exception as exc:
        # Core handlers return domain errors as dictionaries. Unexpected errors
        # should not disclose provider response bodies or credential arguments.
        logger.error("Unhandled %s in MCP tool %s", type(exc).__name__, params.name)
        return _error("internal_error", "The tool could not complete. Check the server logs.")
    if not isinstance(payload, dict):
        logger.error("Non-object result from MCP tool %s", params.name)
        return _error("invalid_tool_result", "The tool returned an unsupported result.")

    return _result(
        payload,
        is_error=payload.get("ok") is False or bool(payload.get("is_error")),
    )


async def _handle_list_resources(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListResourcesResult:
    return ListResourcesResult(
        resources=[
            Resource(
                uri=GUIDE_URI,
                name="Pishkhan usage guide",
                description="How to discover services, connect an account, and follow operations.",
                mime_type="text/plain",
            ),
            Resource(
                uri=TOOLS_URI,
                name="Pishkhan tool contracts",
                description="Current tool descriptions and JSON input schemas.",
                mime_type="application/json",
            ),
        ]
    )


async def _handle_read_resource(
    ctx: ServerRequestContext, params: ReadResourceRequestParams
) -> ReadResourceResult:
    if params.uri == GUIDE_URI:
        text, mime_type = INSTRUCTIONS, "text/plain"
    elif params.uri == TOOLS_URI:
        definitions = await sync_to_async(_list_tool_definitions, thread_sensitive=True)()
        text, mime_type = json.dumps(definitions, ensure_ascii=False), "application/json"
    else:
        from mcp import MCPError

        raise MCPError(-32602, "Unknown resource URI.")
    return ReadResourceResult(contents=[TextResourceContents(uri=params.uri, text=text, mime_type=mime_type)])


async def _handle_list_prompts(
    ctx: ServerRequestContext, params: PaginatedRequestParams | None
) -> ListPromptsResult:
    return ListPromptsResult(
        prompts=[
            Prompt(
                name="pishkhan_task",
                description="Start a Pishkhan service task in Persian or another language.",
                arguments=[PromptArgument(name="request", description="The user's task", required=True)],
            )
        ]
    )


async def _handle_get_prompt(ctx: ServerRequestContext, params: GetPromptRequestParams) -> GetPromptResult:
    arguments = params.arguments or {}
    if params.name != "pishkhan_task" or not arguments.get("request"):
        from mcp import MCPError

        raise MCPError(-32602, "Use pishkhan_task with a non-empty request argument.")
    return GetPromptResult(
        description="Pishkhan service task",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=(
                        f"{arguments['request']}\n\n"
                        "از ابزارهای پیشخوان برای بررسی خدمات و ورودی‌های لازم استفاده کن. "
                        "نتیجهٔ آزمایشی را مشخص کن و وضعیت نهایی عملیات را از ابزار مربوط بگیر."
                    ),
                ),
            )
        ],
    )


def build_server() -> Server:
    """Create a fresh SDK server, suitable for HTTP, stdio, and in-process tests."""
    return Server(
        "PishkhanMCP",
        title="پیشخوان MCP",
        version="0.1.0",
        description="Django-backed tools for Pishkhan services and account workflows.",
        instructions=INSTRUCTIONS,
        website_url="https://github.com/mohamadrezavilani/PishkhanMCP",
        on_list_tools=_handle_list_tools,
        on_call_tool=_handle_call_tool,
        on_list_resources=_handle_list_resources,
        on_read_resource=_handle_read_resource,
        on_list_prompts=_handle_list_prompts,
        on_get_prompt=_handle_get_prompt,
    )


def build_mcp_app(django_application: ASGIApp | None = None) -> Starlette:
    """Serve MCP at /mcp and optionally route other requests to Django.

    This returned app must be the top-level ASGI application. Its lifespan starts
    and stops the SDK session manager; mounting it without entering that lifespan
    would leave HTTP requests without a running manager.
    """
    server = build_server()
    allowed_hosts = getattr(settings, "MCP_ALLOWED_HOSTS", ["localhost:*", "127.0.0.1:*", "testserver"])
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=allowed_hosts,
            allowed_origins=[f"{scheme}://{host}" for host in allowed_hosts for scheme in ("http", "https")],
        ),
    )
    if django_application is not None:
        app.router.routes.append(Mount("/", app=django_application))
    access_key = getattr(settings, "P24_ACCESS_KEY", "")
    if access_key:
        app.add_middleware(MCPAccessKeyMiddleware, access_key=access_key)
    if getattr(settings, "P24_LAN_MODE", False):
        from apps.portal.boundary import LANBoundary

        app.add_middleware(LANBoundary)
    app.state.mcp_server = server
    return app


async def serve_stdio() -> None:
    """Run the same registry through the SDK's standard stdio transport."""
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())
