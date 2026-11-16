"""Synthetic fixtures only. Never replay customer credentials, PAN or raw logs."""

import json
from unittest.mock import Mock

import pytest

from apps.core import operations
from apps.core.errors import PishkhanError
from apps.core.models import AccountSession, Operation, PaymentAttempt, ProviderCall, Quote, UserRequest
from apps.core.tools import call_tool, list_tools
from apps.providers.registry import find_action, search_actions

pytestmark = pytest.mark.django_db


@pytest.fixture
def account():
    return AccountSession.objects.create(mode="live", state="authenticated", token="synthetic-session")


@pytest.fixture
def upstream(monkeypatch):
    responses, calls = [], []

    def invoke(action, parameters, token):
        calls.append((action["path"], parameters))
        if not responses:
            raise AssertionError("Unexpected extra upstream call")
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"status": {"Code": "G00000"}, "parameters": result}

    provider = Mock()
    provider.call.side_effect = invoke
    monkeypatch.setattr(operations, "PishkhanClient", lambda: provider)
    return responses, calls


def call(name, account, **kwargs):
    return call_tool(name, {"session_id": str(account.pk), **kwargs})


def invoice(key="invoice-synthetic", channels=None):
    return {"Invoice": {"PurchaseKey": key, "Amount": 100, "Payable": 100}, "PaymentChannels": channels}


def test_product_exclusions_are_enforced_at_discovery_and_execution(account, upstream):
    assert search_actions(query="taxi")["total"] == 0
    assert call_tool("p24_list_services", {"query": "taxipay"})["total"] == 0
    result = call(
        "p24_execute_action",
        account,
        action_id=find_action("InvoiceRegister", "services")["id"],
        parameters={"Service": "v1_InquiryMunicipalityTaxiFaresBills", "Parameters": "{}"},
        idempotency_key="excluded",
    )
    assert result["error"]["code"] == "SERVICE_NOT_ENABLED"
    assert upstream[1] == []


def test_same_session_distinct_electricity_and_water_requests():
    account = AccountSession.objects.create(mode="demo")
    e = call("p24_electricity_bill", account, bill_id="000100", idempotency_key="e")
    w = call("p24_water_bill", account, bill_id="000200", idempotency_key="w")
    assert e["session_id"] == w["session_id"]
    assert e["request_id"] != w["request_id"]
    assert e["request_id"] != e["operation_id"]
    trace = call("p24_request_trace", account, request_id=e["request_id"])
    assert len(trace["operations"]) == 1
    assert trace["operations"][0]["operation_id"] == e["operation_id"]
    assert trace["request_id_origin"] == "mcp"
    json.dumps(trace)  # MCP structured output must be serializable.


def test_same_key_cannot_relabel_request_service(account):
    one = call("p24_begin_request", account, service_id="electricity", idempotency_key="same")
    two = call("p24_begin_request", account, service_id="water", idempotency_key="same")
    assert one["ok"] and two["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_quote_continuation_preserves_behavior_and_explicit_correlations(account, upstream):
    responses, calls = upstream
    responses.extend(
        [
            {"Active": True},
            invoice(),
            {
                "Query": {"UniqueID": "not-a-bill"},
                "Result": {"UniqueID": "bill-synthetic", "Payment": {"Status": {"Name": "Unpaid"}}},
            },
        ]
    )
    begin = call("p24_begin_request", account, service_id="electricity", idempotency_key="e")
    prepared = call(
        "p24_electricity_bill",
        account,
        request_id=begin["request_id"],
        bill_id="00001",
        idempotency_key="prepare",
    )
    q = prepared["result"]["quote_id"]
    done = call("p24_run_inquiry", account, quote_id=q, idempotency_key="run")
    assert done["request_id"] == begin["request_id"]
    trace = call("p24_request_trace", account, request_id=begin["request_id"])
    assert len(trace["calls"]) == 3
    assert [a[0] for a in calls] == ["v1/ConfigService", "v1/InvoiceRegister", "v1/ElectricBills"]
    assert all(c["upstream_request_id"] is None for c in trace["calls"])
    assert any(
        e["source"]["key"] == "invoice-synthetic" and e["target"]["key"] == "bill-synthetic"
        for e in trace["correlations"]
    )
    assert "not-a-bill" not in json.dumps(trace)
    replay = call("p24_run_inquiry", account, quote_id=q, idempotency_key="different")
    assert replay["replayed"] and len(calls) == 3


def test_cannot_attach_water_to_electricity_request():
    account = AccountSession.objects.create(mode="demo")
    r = call("p24_begin_request", account, service_id="electricity", idempotency_key="e")
    result = call("p24_water_bill", account, request_id=r["request_id"], bill_id="0001", idempotency_key="w")
    assert result["error"]["code"] == "REQUEST_SERVICE_MISMATCH"
    assert not Operation.objects.exists()


def test_foreign_session_request_rejected(account):
    other = AccountSession.objects.create(mode="demo")
    req = call("p24_begin_request", account, idempotency_key="one")
    result = call("p24_request_trace", other, request_id=req["request_id"])
    assert result["error"]["code"] == "REQUEST_NOT_FOUND"


def test_inactive_configuration_does_not_register_invoice(account, upstream):
    upstream[0].append({"Active": False})
    result = call("p24_electricity_bill", account, bill_id="00001", idempotency_key="inactive")
    assert result["status"] == "failed"
    assert result["result"]["error"]["code"] == "SERVICE_DISABLED"
    assert [x[0] for x in upstream[1]] == ["v1/ConfigService"]


def test_unknown_transport_is_traced_and_not_retried(account, upstream):
    upstream[0].append(PishkhanError("UPSTREAM_TIMEOUT", "late", details={"outcome": "unknown"}))
    kwargs = {
        "action_id": find_action("ConfigBasic", "core")["id"],
        "parameters": {},
        "idempotency_key": "timeout",
    }
    first = call("p24_execute_action", account, **kwargs)
    second = call("p24_execute_action", account, **kwargs)
    assert first["status"] == "unknown" and second["replayed"]
    assert len(upstream[1]) == 1 and ProviderCall.objects.get().status == "unknown"


@pytest.mark.parametrize(
    "status,financial,settled",
    [
        ("Unknown", "unknown", False),
        ("Undefined", "unknown", False),
        ("Unpaid", "requires_user_action", False),
        ("Paid", "paid_waiting_settlement", False),
        ("InProcess", "processing", False),
        ("Settle", "settled", True),
        ("Return", "returned", False),
        ("Unpayable", "unpayable", False),
    ],
)
def test_payment_info_enum_not_http_success_controls_state(account, upstream, status, financial, settled):
    request = UserRequest.objects.create(session=account, client_key="payment")
    PaymentAttempt.objects.create(
        session=account, request=request, payment_key="a" * 32, gateway="OnlinePayment_Test"
    )
    upstream[0].append(
        {
            "Status": {"Name": status},
            "ExtraInfo": {"TraceNumber": "synthetic"},
            "Bills": [{"UniqueID": "bill-1", "Payment": {"Status": {"Name": "Unpaid"}}}],
        }
    )
    result = call("p24_payment_status", account, payment_key="a" * 32)
    assert result["financial_state"] == financial and result["settled"] is settled
    assert result["bill_statuses"] == [{"bill_id": "bill-1", "status": "Unpaid"}]
    assert result["authority"] == "core.svc/v1/PaymentInfo"


def test_ipg_then_status_updates_original_payment_operation(account, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return"
    responses, calls = upstream
    channels = [{"Active": True, "Gateways": [{"Active": True, "Type": {"Name": "OnlinePayment_Test"}}]}]
    responses.extend(
        [{}, invoice(channels=channels), {"PaymentKey": "a" * 32, "RedirectLink": "https://gateway.example"}]
    )
    q = call("p24_electricity_bill", account, bill_id="00001", idempotency_key="e")["result"]["quote_id"]
    paid = call(
        "p24_pay_quote",
        account,
        quote_id=q,
        gateway="OnlinePayment_Test",
        use_credit=False,
        idempotency_key="pay",
    )
    assert paid["status"] == "requires_user_action" and not Quote.objects.get(pk=q).parameters.get(
        "payment_completed"
    )
    responses.append({"Status": {"Name": "Paid"}})
    status = call("p24_payment_status", account, payment_key="a" * 32)
    assert not status["settled"] and Operation.objects.get(pk=paid["operation_id"]).status == "pending"
    responses.append({"Status": {"Name": "Settle"}})
    call("p24_payment_status", account, payment_key="a" * 32)
    assert Operation.objects.get(pk=paid["operation_id"]).status == "completed"
    assert sum(path == "v1/InvoicePayment" for path, _ in calls) == 1


def test_bills_payment_has_bill_links_and_no_electricity_assumption(account, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return"
    channels = [{"Gateways": [{"Type": {"Name": "CNPG_Test"}}]}]
    upstream[0].extend([{"PaymentChannels": channels}, {"PaymentKey": "b" * 32}])
    request = call("p24_begin_request", account, service_id="water", idempotency_key="water")
    p = call(
        "p24_prepare_bill_payment",
        account,
        request_id=request["request_id"],
        bill_ids=["water-bill"],
        gateway="CNPG_Test",
        idempotency_key="p",
    )
    assert p["status"] == "requires_user_action" and p["result"]["payment_flow"] == "cnpg"
    assert upstream[1][0][1]["Service"] == "v1_InquiryWaterBills"
    trace = call("p24_request_trace", account, request_id=request["request_id"])
    assert any(
        e["source"]["type"] == "BillUniqueID" and e["target"]["type"] == "PaymentKey"
        for e in trace["correlations"]
    )


def test_inactive_gateway_is_not_accepted(account, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return"
    upstream[0].extend(
        [{}, invoice(channels=[{"Active": False, "Gateways": [{"Type": {"Name": "CNPG_Test"}}]}])]
    )
    q = call("p24_electricity_bill", account, bill_id="00001", idempotency_key="e")["result"]["quote_id"]
    p = call("p24_pay_quote", account, quote_id=q, gateway="CNPG_Test", use_credit=False, idempotency_key="p")
    assert p["error"]["code"] == "INVALID_GATEWAY"
    assert len(upstream[1]) == 2


def test_cnpg_payload_redacted_and_unknown_not_repaid(account, upstream):
    req = UserRequest.objects.create(session=account, client_key="cnpg")
    PaymentAttempt.objects.create(session=account, request=req, payment_key="c" * 32, gateway="CNPG_Test")
    upstream[0].append(PishkhanError("UPSTREAM_TIMEOUT", "late", details={"outcome": "unknown"}))
    first = call(
        "p24_cnpg_payment",
        account,
        payment_key="c" * 32,
        encrypted_data="secret-ciphertext",
        idempotency_key="p",
    )
    again = call(
        "p24_cnpg_payment",
        account,
        payment_key="c" * 32,
        encrypted_data="another-ciphertext",
        idempotency_key="new",
    )
    assert first["status"] == "unknown" and again["replayed"]
    assert len(upstream[1]) == 1
    assert "secret-ciphertext" not in json.dumps(Operation.objects.get().request_data)


def test_cnpg_success_still_reconciles_payment_info(account, upstream):
    req = UserRequest.objects.create(session=account, client_key="cnpg-success")
    PaymentAttempt.objects.create(session=account, request=req, payment_key="d" * 32, gateway="CNPG_Test")
    upstream[0].extend([{"TransactionTraceNumber": "synthetic"}, {"Status": {"Name": "Paid"}}])
    result = call(
        "p24_cnpg_payment", account, payment_key="d" * 32, encrypted_data="ciphertext", idempotency_key="p"
    )
    assert result["status"] == "pending"
    assert [x[0] for x in upstream[1]] == ["v1/CnpgPayment", "v1/PaymentInfo"]


def test_browser_callback_never_marks_payment_success(client, account):
    attempt = PaymentAttempt.objects.create(session=account, payment_key="e" * 32)
    response = client.get("/payments/return/?status=success&PaymentKey=" + "e" * 32)
    assert response.status_code == 200
    attempt.refresh_from_db()
    assert attempt.status == "Unknown"
    assert not any("webhook" in t["name"].lower() for t in list_tools())
