"""Reported mobile inquiry/gateway chain, using synthetic data and no live calls."""

import json
from unittest.mock import Mock

import httpx
import pytest
from django.db.models.query import QuerySet

from apps.agent import runner
from apps.catalog.catalog import list_services
from apps.core import operations, payments
from apps.core.errors import PishkhanError
from apps.core.models import (
    AccountSession,
    Conversation,
    Operation,
    PaymentAttempt,
    ProviderCall,
    Quote,
    UserRequest,
)
from apps.core.tools import call_tool
from apps.core.tracing import tool_scope

pytestmark = pytest.mark.django_db
PHONE = "09120000000"
BILL = "synthetic-bill"
GATEWAY = "OnlinePayment_Synthetic"
SERVICE = "v1_InquiryCellPhoneBills"


@pytest.fixture
def account(settings):
    settings.P24_MODE = "live"
    settings.P24_PAYMENT_CALLBACK = ""
    settings.P24_ACCESS_KEY = ""
    return AccountSession.objects.create(mode="live", state="authenticated", token="synthetic-token")


@pytest.fixture
def provider(monkeypatch):
    calls = []
    choices = [GATEWAY, "Wallet_Internal_Synthetic"]

    def invoke(action, parameters, token):
        endpoint = action["path"].split("/")[-1]
        calls.append((endpoint, parameters))
        data = {
            "ConfigService": {"Active": True},
            "InvoiceRegister": {"Invoice": {"PurchaseKey": "synthetic-invoice", "Amount": 0, "Payable": 0}},
            "CellPhoneBills": {
                "Query": {
                    "UniqueID": "not-a-bill",
                    "Parameters": [
                        {"Key": "Operator", "Value": "Mci"},
                        {"Key": "LineNumber", "Value": PHONE},
                    ],
                },
                "Result": [
                    {
                        "UniqueID": BILL,
                        "Amount": 92000,
                        "ExtraInfo": {"Final": False},
                        "Type": {"Name": "CellPhoneMci"},
                        "Payment": {"Status": {"Name": "Unpaid"}},
                    }
                ],
            },
            "BillsPaymentChannels": {
                "PaymentChannels": [
                    {
                        "Active": True,
                        "Gateways": [{"Active": True, "Type": {"Name": name}} for name in choices],
                    }
                ]
            },
            "BillsPayment": {"PaymentKey": "synthetic-payment", "RedirectLink": "https://bank.example/pay"},
            "PaymentInfo": {"Status": {"Name": "Unpaid"}, "Amount": 92000, "Fee": 1500, "TotalAmount": 93500},
        }
        assert endpoint in data, endpoint
        return {"status": {"Code": "G00000"}, "parameters": data[endpoint]}

    client = Mock()
    client.call.side_effect = invoke
    monkeypatch.setattr(operations, "PishkhanClient", lambda: client)
    return calls, choices


def begin(account, service_id="mci"):
    return call_tool(
        "p24_begin_request",
        {
            "session_id": str(account.pk),
            "service_id": service_id,
            "idempotency_key": "behavior-" + service_id,
        },
    )["request_id"]


def inquire(account, request_id=None):
    args = {"session_id": str(account.pk), "phone": PHONE, "operator": "mci", "idempotency_key": "mobile"}
    if request_id:
        args["request_id"] = request_id
    prepared = call_tool("p24_mobile_bill", args)
    assert prepared["ok"], prepared
    return call_tool(
        "p24_run_inquiry",
        {
            "session_id": str(account.pk),
            "quote_id": prepared["result"]["quote_id"],
            "idempotency_key": "result",
        },
    )


def prepare(account, request_id, gateway):
    return call_tool(
        "p24_prepare_bill_payment",
        {
            "session_id": str(account.pk),
            "request_id": request_id,
            "bill_ids": [BILL],
            "service_name": SERVICE,
            "gateway": gateway,
            "idempotency_key": "client-" + gateway,
        },
    )


def test_mobile_catalog_query_no_longer_misses_mci():
    query = "\u0642\u0628\u0636 \u0647\u0645\u0631\u0627\u0647 \u0627\u0648\u0644 \u0645\u0648\u0628\u0627\u06cc\u0644"
    assert [s["id"] for s in list_services(query=query)] == ["mci"]


@pytest.mark.parametrize(
    "operator,service", [("MCI", "mci"), ("mci", "mci"), ("Irancell", "irancell"), ("RIGHTEL", "rightel")]
)
def test_shared_endpoint_maps_operator_not_first_service(account, provider, operator, service):
    request_id = begin(account, service)
    result = call_tool(
        "p24_prepare_inquiry",
        {
            "session_id": str(account.pk),
            "request_id": request_id,
            "action_id": "services_cell_phone_bills_v1",
            "parameters": {"LineNumber": PHONE, "Operator": operator},
            "idempotency_key": "prepare",
        },
    )
    assert result["ok"], result
    assert result["service_id"] == service
    assert result["request_id"] == request_id
    assert result["result"]["service_id"] == service
    quote = Quote.objects.get(pk=result["result"]["quote_id"])
    assert quote.request.service_id == service
    assert quote.parameters["input"]["Operator"].casefold() == service


def test_operator_cannot_be_attached_to_other_service(account, provider):
    result = call_tool(
        "p24_mobile_bill",
        {
            "session_id": str(account.pk),
            "request_id": begin(account, "irancell"),
            "phone": PHONE,
            "operator": "mci",
            "idempotency_key": "wrong-service",
        },
    )
    assert result["error"]["code"] == "REQUEST_SERVICE_MISMATCH"
    assert not provider[0]


def test_empty_request_is_bound_to_actual_operator(account, provider):
    request = UserRequest.objects.create(session=account, client_key="empty")
    result = inquire(account, str(request.pk))
    assert result["service_id"] == "mci"
    request.refresh_from_db()
    assert request.service_id == "mci"


def test_recent_bills_recovers_legacy_mislabel_without_fabricating_or_reinquiring(account, provider):
    result = inquire(account)
    # Reproduce old metadata while retaining the original successful Core payload.
    Operation.objects.filter(pk=result["operation_id"]).update(service_id="irancell")
    UserRequest.objects.filter(pk=result["request_id"]).update(service_id="irancell")
    before = len(provider[0])
    recovered = call_tool(
        "p24_recent_bills", {"session_id": str(account.pk), "service_id": "mci", "phone": PHONE}
    )
    assert len(provider[0]) == before
    assert len(recovered["items"]) == 1
    row = recovered["items"][0]
    assert row["bill_id"] == BILL and row["bill_id"] != "not-a-bill"
    assert row["recorded_service_id"] == "irancell" and row["service_id"] == "mci"
    assert row["request_id"] == result["request_id"]
    assert row["service_name"] == SERVICE and row["amount"] == 92000
    assert not row["fresh_inquiry"]
    other = AccountSession.objects.create(mode="live")
    assert call_tool("p24_recent_bills", {"session_id": str(other.pk)})["items"] == []


def test_invalid_gateway_can_be_corrected_on_same_reservation(account, provider):
    request_id = inquire(account)["request_id"]
    failed = prepare(account, request_id, "IPG")
    assert failed["result"]["error"]["code"] == "INVALID_GATEWAY"
    assert not any(c[0] == "BillsPayment" for c in provider[0])
    corrected = prepare(account, request_id, GATEWAY)
    assert corrected["ok"], corrected
    assert corrected["operation_id"] == failed["operation_id"]
    assert corrected["request_id"] == request_id
    assert corrected["result"]["preflight_recovery"]["reason"] == "INVALID_GATEWAY"
    assert prepare(account, request_id, GATEWAY)["replayed"]
    assert len([c for c in provider[0] if c[0] == "BillsPayment"]) == 1


@pytest.mark.parametrize("evidence", ["charge_call", "attempt", "reference", "unknown"])
def test_gateway_recovery_never_reissues_a_possible_payment(account, provider, evidence):
    request_id = inquire(account)["request_id"]
    old = prepare(account, request_id, "IPG")
    op = Operation.objects.get(pk=old["operation_id"])
    if evidence == "charge_call":
        ProviderCall.objects.create(session=account, operation=op, action_id="core_bills_payment_v1")
    elif evidence == "attempt":
        PaymentAttempt.objects.create(session=account, operation=op, payment_key="already-issued")
    elif evidence == "reference":
        op.upstream_reference = "possibly-issued"
        op.save(update_fields=["upstream_reference"])
    else:
        op.status = "unknown"
        op.save(update_fields=["status"])
    count = len(provider[0])
    result = prepare(account, request_id, GATEWAY)
    assert not result["ok"]
    assert len(provider[0]) == count


def test_gateway_recovery_refuses_service_or_request_change(account, provider):
    rid = inquire(account)["request_id"]
    prepare(account, rid, "IPG")
    other = begin(account, "water")
    result = prepare(account, other, GATEWAY)
    assert result["error"]["code"] == "REQUEST_MISMATCH"
    with pytest.raises(PishkhanError) as error:
        with tool_scope({"session_id": str(account.pk)}, rid):
            payments.prepare_bill_payment(str(account.pk), [BILL], GATEWAY, "new", "different-service")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert not any(c[0] == "BillsPayment" for c in provider[0])


def test_losing_gateway_recovery_claim_does_not_send_payment(account, provider, monkeypatch):
    rid = inquire(account)["request_id"]
    old = prepare(account, rid, "IPG")
    update = QuerySet.update

    def race(qs, **values):
        if qs.model is Operation and values.get("status") == "running":
            update(Operation.objects.filter(pk=old["operation_id"]), status="running")
        return update(qs, **values)

    monkeypatch.setattr(QuerySet, "update", race)
    result = prepare(account, rid, GATEWAY)
    assert result["replayed"] and result["status"] == "running"
    assert not any(c[0] == "BillsPayment" for c in provider[0])


def test_browser_link_recovers_failed_gateway_and_reads_actual_fees(account, provider):
    rid = inquire(account)["request_id"]
    old = prepare(account, rid, "IPG")
    result = call_tool(
        "p24_bill_payment_link",
        {"session_id": str(account.pk), "request_id": rid, "bill_ids": [BILL], "idempotency_key": "link"},
    )
    assert result["ok"], result
    assert result["operation_id"] == old["operation_id"] and result["request_id"] == rid
    assert result["result"]["parameters"]["RedirectLink"] == "https://bank.example/pay"
    assert result["payment_info"]["fee"] == 1500
    assert result["payment_info"]["total_amount"] == 93500
    assert result["payment_info"]["payment_status"] == "Unpaid"
    assert not any(c[0] in {"WalletPayment", "CnpgPayment"} for c in provider[0])


def test_link_does_not_substitute_wallet_when_ipg_unavailable(account, provider):
    inquire(account)
    provider[1][:] = ["Wallet_Internal_Synthetic"]
    result = call_tool(
        "p24_bill_payment_link",
        {"session_id": str(account.pk), "bill_ids": [BILL], "idempotency_key": "link"},
    )
    assert result["error"]["code"] == "BROWSER_GATEWAY_UNAVAILABLE"
    assert not PaymentAttempt.objects.exists()


def test_query_identifier_is_not_accepted_as_bill(account, provider):
    inquire(account)
    result = call_tool(
        "p24_bill_payment_link",
        {"session_id": str(account.pk), "bill_ids": ["not-a-bill"], "idempotency_key": "link"},
    )
    assert result["error"]["code"] == "BILL_NOT_FOUND"


def test_history_recovery_api_is_session_scoped(account, client):
    row = Conversation.objects.create(session=account, messages=[{"role": "user", "content": "continue"}])
    listing = client.get("/api/conversations/", {"session_id": str(account.pk)}).json()
    assert listing["items"][0]["conversation_id"] == str(row.pk)
    detail = client.get(f"/api/conversations/{row.pk}/", {"session_id": str(account.pk)}).json()
    assert detail["messages"][0]["content"] == "continue"
    other = AccountSession.objects.create(mode="live")
    assert client.get(f"/api/conversations/{row.pk}/", {"session_id": str(other.pk)}).status_code == 404


def test_agent_two_tool_continuation_reuses_bill_without_paper_ids(account, provider, settings, monkeypatch):
    inquire(account)
    settings.AGENT_BASE_URL = "https://model.example/v1"
    settings.AGENT_MODEL = "test"
    settings.AGENT_MAX_STEPS = 12
    settings.AGENT_DAILY_MESSAGE_LIMIT = 10
    counter = 0

    def model(request):
        nonlocal counter
        counter += 1
        if counter == 1:
            name, args = "p24_recent_bills", {"service_id": "mci", "phone": PHONE}
        elif counter == 2:
            saved = json.loads(json.loads(request.content)["messages"][-1]["content"])["items"][0]
            name, args = (
                "p24_bill_payment_link",
                {"bill_ids": [saved["bill_id"]], "request_id": saved["request_id"]},
            )
        else:
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "Synthetic link prepared, not paid."}}]}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call-{counter}",
                                    "function": {"name": name, "arguments": json.dumps(args)},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(runner, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(model)))
    before = len([c for c in provider[0] if c[0] == "CellPhoneBills"])
    result = runner.run_turn(str(account.pk), "Create only a link for the same mobile bill")
    assert result["ok"] and result["steps"] == 3
    assert len(result["tool_calls"]) == 2
    assert result["agent_usage"]["used"] == 1
    assert len([c for c in provider[0] if c[0] == "CellPhoneBills"]) == before


def test_reported_mci_prepare_regression(account, provider):
    rid = begin(account)
    result = call_tool(
        "p24_prepare_inquiry",
        {
            "session_id": str(account.pk),
            "request_id": rid,
            "action_id": "services_cell_phone_bills_v1",
            "parameters": {"LineNumber": PHONE, "Operator": "Mci"},
            "service_name": SERVICE,
            "idempotency_key": "prepare-regression",
        },
    )
    assert result["ok"], result
    assert result["service_id"] == "mci"


def test_reported_gateway_correction_regression(account, provider):
    rid = begin(account)
    failed = prepare(account, rid, "IPG")
    assert failed["result"]["error"]["code"] == "INVALID_GATEWAY"
    fixed = prepare(account, rid, GATEWAY)
    assert fixed["ok"], fixed
    assert fixed["operation_id"] == failed["operation_id"]
    assert len([c for c in provider[0] if c[0] == "BillsPayment"]) == 1


def test_step_limit_exposes_real_last_tool_error(account, settings, monkeypatch):
    settings.AGENT_BASE_URL = "https://model.example/v1"
    settings.AGENT_MODEL = "test"
    settings.AGENT_MAX_STEPS = 1
    settings.AGENT_DAILY_MESSAGE_LIMIT = 10
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "x",
                            "function": {
                                "name": "p24_begin_request",
                                "arguments": json.dumps({"service_id": "mobile-bill"}),
                            },
                        }
                    ]
                }
            }
        ]
    }
    monkeypatch.setattr(
        runner,
        "_make_client",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))),
    )
    result = runner.run_turn(str(account.pk), "test")
    assert result["stop_reason"] == "agent_step_limit"
    assert result["progress"]["last_tool_error"]["error"]["code"] == "UNKNOWN_SERVICE"
    assert "UNKNOWN_SERVICE" in result["reply"]


def test_repeated_link_reuses_payment_even_if_available_gateways_change(account, provider):
    rid = inquire(account)["request_id"]
    args = {"session_id": str(account.pk), "request_id": rid, "bill_ids": [BILL], "idempotency_key": "link"}
    first = call_tool("p24_bill_payment_link", args)
    provider[1][:] = ["OnlinePayment_New"]
    again = call_tool("p24_bill_payment_link", {**args, "idempotency_key": "different-client-key"})
    assert first["ok"] and again["ok"] and again["replayed"]
    assert first["operation_id"] == again["operation_id"]
    assert len([c for c in provider[0] if c[0] == "BillsPayment"]) == 1


def test_settled_bill_does_not_get_new_link(account, provider):
    result = inquire(account)
    op = Operation.objects.get(pk=result["operation_id"])
    op.result["parameters"]["Result"][0]["Payment"]["Status"]["Name"] = "Settle"
    op.save(update_fields=["result"])
    count = len(provider[0])
    link = call_tool(
        "p24_bill_payment_link",
        {"session_id": str(account.pk), "bill_ids": [BILL], "idempotency_key": "no-charge"},
    )
    assert link["error"]["code"] == "BILL_NOT_PAYABLE"
    assert len(provider[0]) == count


def test_console_state_in_node():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed; API/history tests remain active")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "scripts/test_console_state.cjs")], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"]
