"""Small acceptance run; --live performs bootstrap/config only, never payment/OTP."""

import json
import uuid

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.tools import call_tool


class Command(BaseCommand):
    help = "Validate demo behavior/receipt/trace and optional HTTP MCP. --live checks only device/config."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url", default="", help="Running Uvicorn base URL; omit for in-process tools."
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Only DeviceRegister and ConfigBasic; never sends OTP or pays.",
        )

    def handle(self, *args, **options):
        base = options["base_url"].rstrip("/")
        headers = {}
        if settings.P24_ACCESS_KEY:
            headers["Authorization"] = "Bearer " + settings.P24_ACCESS_KEY
        checks = []
        with httpx.Client(timeout=45, headers=headers, trust_env=False) as client:

            def call(name, arguments):
                try:
                    if base:
                        response = client.post(
                            base + "/api/tools/call/", json={"name": name, "arguments": arguments}
                        )
                        result = response.json()
                    else:
                        result = call_tool(name, arguments)
                except (httpx.RequestError, ValueError) as exc:
                    raise CommandError(f"{name}: HTTP/JSON failure ({type(exc).__name__}).") from exc
                if not result.get("ok"):
                    error = result.get("error") or result.get("result", {}).get("error", {})
                    raise CommandError(f"{name}: {error.get('code', result.get('status', 'failed'))}")
                return result

            capabilities = call("p24_capabilities", {})
            mode = capabilities["mode"]
            wanted = "live" if options["live"] else "demo"
            if mode != wanted:
                raise CommandError(f"Expected {wanted}, server is {mode}. Restart after changing P24_MODE.")
            if call("p24_list_services", {"query": "taxipay"})["total"] != 0:
                raise CommandError("Product scope still exposes taxi.")
            checks.append("product_scope")
            session = call("p24_create_session", {})
            sid = session["session_id"]
            common = {"session_id": sid}
            if options["live"]:
                if session.get("bootstrap") != "completed":
                    err = session.get("bootstrap_error", {})
                    raise CommandError(
                        f"DeviceRegister failed: {err.get('code')}, upstream={err.get('details', {}).get('upstream_code')}. No OTP/payment attempted."
                    )
                call(
                    "p24_execute_action",
                    {
                        **common,
                        "action_id": "core_config_basic_v1",
                        "parameters": {},
                        "idempotency_key": "smoke-config-" + uuid.uuid4().hex,
                    },
                )
                checks += ["live_device_register", "live_config_basic"]
            else:
                call("p24_request_otp", {**common, "phone": "09000000000", "idempotency_key": "smoke-otp"})
                call(
                    "p24_verify_otp",
                    {**common, "phone": "09000000000", "otp": "123456", "idempotency_key": "smoke-login"},
                )
                e = call(
                    "p24_electricity_bill", {**common, "bill_id": "000100", "idempotency_key": "smoke-e"}
                )
                w = call("p24_water_bill", {**common, "bill_id": "000200", "idempotency_key": "smoke-w"})
                if e["request_id"] == w["request_id"]:
                    raise CommandError("Water and electricity were incorrectly grouped.")
                replay = call(
                    "p24_electricity_bill", {**common, "bill_id": "000100", "idempotency_key": "smoke-e"}
                )
                if replay["operation_id"] != e["operation_id"] or not replay.get("replayed"):
                    raise CommandError("Idempotent replay failed.")
                p = call(
                    "p24_prepare_bill_payment",
                    {
                        **common,
                        "request_id": e["request_id"],
                        "bill_ids": ["DEMO-BILL"],
                        "gateway": "demo",
                        "idempotency_key": "smoke-pay",
                    },
                )
                call("p24_demo_complete_payment", {**common, "operation_id": p["operation_id"]})
                receipt = call("p24_get_receipt", {**common, "operation_id": p["operation_id"]})
                if (
                    not receipt["receipt_available"]
                    or receipt["receipt"].get("real_money_moved") is not False
                ):
                    raise CommandError("Demo receipt invariant failed.")
                for rid in (e["request_id"], w["request_id"]):
                    trace = call("p24_request_trace", {**common, "request_id": rid})
                    if not trace["operations"]:
                        raise CommandError("Request trace is empty.")
                checks += [
                    "demo_login",
                    "distinct_requests_same_session",
                    "idempotent_replay",
                    "demo_payment_receipt",
                    "request_trace",
                ]
            if base:
                rpc_headers = {
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2025-11-25",
                }

                def rpc(method, params, rpc_id):
                    response = client.post(
                        base + "/mcp",
                        headers=rpc_headers,
                        json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
                    )
                    response.raise_for_status()
                    body = response.json()
                    if "error" in body:
                        raise CommandError(f"MCP {method} failed.")
                    return body["result"]

                rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "p24-smoke", "version": "1"},
                    },
                    1,
                )
                notify = client.post(
                    base + "/mcp",
                    headers=rpc_headers,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                )
                if notify.status_code != 202:
                    raise CommandError("MCP initialization notification failed.")
                listing = rpc("tools/list", {}, 2)
                if "p24_request_trace" not in {tool["name"] for tool in listing["tools"]}:
                    raise CommandError("MCP request trace tool missing.")
                result = rpc("tools/call", {"name": "p24_capabilities", "arguments": {}}, 3)
                if result.get("isError") or not result["structuredContent"]["ok"]:
                    raise CommandError("MCP tool execution failed.")
                checks.append("http_mcp_initialize_list_call")
        self.stdout.write(
            json.dumps(
                {
                    "ok": True,
                    "mode": mode,
                    "session_id": sid,
                    "checks": checks,
                    "real_otp_sent": False,
                    "real_payment_attempted": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
