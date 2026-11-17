"""Synthetic LAN checkout, status feedback, history cards and 50-turn regressions."""

import json
import uuid
from unittest.mock import Mock

import httpx
import pytest
from django.test import Client
from django.utils import timezone

from apps.agent import runner
from apps.core.errors import PishkhanError
from apps.core.models import (
    AccountSession,
    AgentDailyUsage,
    Conversation,
    Operation,
    PaymentAttempt,
    UserRequest,
)
from apps.portal import checkout, views
from apps.portal.models import Visitor

pytestmark = pytest.mark.django_db


@pytest.fixture
def browser_user(settings):
    settings.P24_MODE = "live"
    settings.P24_PAYMENT_CALLBACK = ""
    settings.P24_AUTO_BILL_LINKS = True
    settings.AGENT_BASE_URL = "https://synthetic.example/v1"
    settings.AGENT_MODEL = "synthetic"
    client = Client(enforce_csrf_checks=True)
    client.get("/")
    client.get("/api/portal/state/")
    visitor = Visitor.objects.get(pk=client.session["portal_visitor"])
    visitor.account = AccountSession.objects.create(mode="live", state="authenticated", token="fake")
    visitor.save()
    return client, visitor


def post(client, path, payload):
    return client.post(
        "/api/portal/" + path,
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )


def saved_inquiry(visitor, amounts=(92000,), status="Unpaid"):
    req = UserRequest.objects.create(session=visitor.account, service_id="mci", client_key=uuid.uuid4().hex)
    return Operation.objects.create(
        session=visitor.account,
        request=req,
        action_id="services_cell_phone_bills_v1",
        service_id="mci",
        idempotency_key=uuid.uuid4().hex,
        request_hash="synthetic",
        status="completed",
        result={
            "stage": "completed",
            "status": {"Code": "G00000"},
            "parameters": {
                "Query": {
                    "Parameters": [
                        {"Key": "LineNumber", "Value": "09120000000"},
                        {"Key": "Operator", "Value": "Mci"},
                    ]
                },
                "Result": [
                    {
                        "UniqueID": f"synthetic-bill-{i}",
                        "Amount": amount,
                        "Payment": {"Status": {"Name": status}},
                        "ExtraInfo": {"Final": bool(i)},
                    }
                    for i, amount in enumerate(amounts)
                ],
            },
        },
    )


def trace(op):
    return [{"name": "p24_run_inquiry", "result": {"ok": True, "operation_id": str(op.pk)}}]


@pytest.fixture
def upstream(monkeypatch):
    state = {"paid": False, "calls": [], "fail": None}

    def call(self, action, parameters, token=""):
        endpoint = action["path"].split("/")[-1]
        state["calls"].append(endpoint)
        if endpoint == state["fail"]:
            raise PishkhanError("UPSTREAM_TIMEOUT", "Synthetic timeout", details={"outcome": "unknown"})
        if endpoint == "ConfigService":
            data = {"Active": True}
        elif endpoint == "InvoiceRegister":
            data = {"Invoice": {"PurchaseKey": "synthetic-invoice", "Amount": 0, "Payable": 0}}
        elif endpoint == "CellPhoneBills":
            data = {
                "Query": {
                    "Parameters": [
                        {"Key": "LineNumber", "Value": "09120000000"},
                        {"Key": "Operator", "Value": "Mci"},
                    ]
                },
                "Result": [
                    {
                        "UniqueID": "synthetic-bill-0",
                        "Amount": 92000,
                        "Payment": {"Status": {"Name": "Unpaid"}},
                        "ExtraInfo": {"Final": False},
                    }
                ],
            }
        elif endpoint == "BillsPaymentChannels":
            data = {
                "PaymentChannels": [
                    {
                        "Active": True,
                        "Gateways": [{"Type": {"Name": "OnlinePayment_Sadad_Ghabzino"}, "Active": True}],
                    }
                ]
            }
        elif endpoint == "BillsPayment":
            assert parameters["Bills"] == ["synthetic-bill-0"]
            data = {"PaymentKey": "synthetic-key", "RedirectLink": "https://bank.example/pay"}
        elif endpoint == "PaymentInfo":
            status = "Paid" if state["paid"] else "Unpaid"
            data = {
                "Status": {"Name": status},
                "Amount": 92000,
                "Fee": 0,
                "TotalAmount": 92000,
                "Bills": [{"UniqueID": "synthetic-bill-0", "Payment": {"Status": {"Name": status}}}],
            }
        else:
            raise AssertionError("Unexpected upstream call: " + endpoint)
        return {"status": {"Code": "G00000"}, "parameters": data}

    monkeypatch.setattr("apps.core.operations.PishkhanClient.call", call)
    return state


def test_fresh_unpaid_inquiry_prepares_one_link_not_payment(browser_user, upstream):
    _, user = browser_user
    op = saved_inquiry(user)
    result = checkout.prepare_inquiry_links(user, trace(op))
    assert result["entries"][0]["result"]["payment_info"]["total_amount"] == 92000
    assert upstream["calls"].count("BillsPayment") == 1
    assert set(upstream["calls"]) == {"BillsPaymentChannels", "BillsPayment", "PaymentInfo"}
    assert PaymentAttempt.objects.get().request_id == op.request_id
    checkout.prepare_inquiry_links(user, trace(op))
    assert upstream["calls"].count("BillsPayment") == 1


@pytest.mark.parametrize(
    "amount,status", [(0, "Unpaid"), (92000, "Paid"), (92000, "Settle"), (None, "Unpaid"), (True, "Unpaid")]
)
def test_no_link_for_zero_paid_unknown_or_invalid_amount(browser_user, upstream, amount, status):
    _, user = browser_user
    result = checkout.prepare_inquiry_links(user, trace(saved_inquiry(user, (amount,), status)))
    assert not result["entries"]
    assert not upstream["calls"]


def test_multiple_payable_terms_require_selection(browser_user, upstream):
    _, user = browser_user
    result = checkout.prepare_inquiry_links(user, trace(saved_inquiry(user, (92000, 100000))))
    assert result["notices"][0]["code"] == "BILL_SELECTION_REQUIRED"
    assert not upstream["calls"]


def test_zero_term_and_one_payable_term_are_unambiguous(browser_user, upstream):
    _, user = browser_user
    result = checkout.prepare_inquiry_links(user, trace(saved_inquiry(user, (92000, 0))))
    assert len(result["entries"]) == 1


@pytest.mark.parametrize(
    "message",
    [
        "inquiry only",
        "no payment link",
        "\u0641\u0642\u0637 \u0627\u0633\u062a\u0639\u0644\u0627\u0645",
        "\u0644\u06cc\u0646\u06a9 \u0646\u0633\u0627\u0632",
    ],
)
def test_explicit_opt_out(message):
    assert not checkout.link_preparation_enabled(message, True)
    assert not checkout.link_preparation_enabled("check my bill", False)


def test_foreign_operation_cannot_trigger_automatic_link(browser_user, upstream):
    _, user = browser_user
    other = Visitor.objects.create(account=AccountSession.objects.create(mode="live"))
    checkout.prepare_inquiry_links(user, trace(saved_inquiry(other)))
    assert not upstream["calls"]


def test_history_and_state_reads_never_prepare_links(browser_user, upstream):
    client, user = browser_user
    saved_inquiry(user)
    conversation = Conversation.objects.create(session=user.account)
    client.get("/api/portal/state/")
    client.get(f"/api/portal/history/{conversation.pk}/")
    assert not upstream["calls"]


def test_failed_link_does_not_erase_successful_inquiry(browser_user, upstream):
    _, user = browser_user
    op = saved_inquiry(user)
    upstream["fail"] = "BillsPayment"
    result = checkout.prepare_inquiry_links(user, trace(op))
    assert result["notices"][0]["code"] == "UPSTREAM_TIMEOUT"
    op.refresh_from_db()
    assert op.status == "completed"
    checkout.prepare_inquiry_links(user, trace(op))
    assert upstream["calls"].count("BillsPayment") == 1


def test_status_button_same_status_and_paid_feedback_without_model(browser_user, upstream, monkeypatch):
    client, user = browser_user
    checkout.prepare_inquiry_links(user, trace(saved_inquiry(user)))
    model = Mock(side_effect=AssertionError("Status cannot call the model"))
    monkeypatch.setattr(runner, "_make_client", model)
    for paid in (False, False, True):
        upstream["paid"] = paid
        before = list(upstream["calls"])
        r = post(client, "payment/", {"action": "status", "payment_key": "synthetic-key"})
        assert r.status_code == 200, r.content
        update = r.json()["payment_update"]
        assert update["message"] and update["checked_at"]
        assert update["payment_complete"] == paid
        card = r.json()["payments"][0]
        assert card["last_checked_at"]
        assert card["payment_complete"] == paid
        assert bool(card["redirect_url"]) != paid
        assert upstream["calls"][len(before) :] == ["PaymentInfo"]
    assert not AgentDailyUsage.objects.exists()
    model.assert_not_called()


def test_status_failure_is_visible_and_retains_last_observation(browser_user, upstream):
    client, user = browser_user
    checkout.prepare_inquiry_links(user, trace(saved_inquiry(user)))
    upstream["fail"] = "PaymentInfo"
    r = post(client, "payment/", {"action": "status", "payment_key": "synthetic-key"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UPSTREAM_TIMEOUT"
    card = client.get("/api/portal/state/").json()["payments"][0]
    assert card["fee"] == 0 and not card["payment_complete"]


def test_chat_auto_link_and_reload_preserve_current_card(browser_user, upstream, monkeypatch):
    client, user = browser_user
    op = saved_inquiry(user)
    convo = Conversation.objects.create(session=user.account, messages=[{"role": "user", "content": "bill"}])
    run = Mock(
        return_value={
            "ok": True,
            "reply": "Synthetic bill",
            "conversation_id": str(convo.pk),
            "tool_calls": trace(op),
        }
    )
    monkeypatch.setattr(views, "run_turn", run)
    payload = {"message": "check bill", "client_key": str(uuid.uuid4()), "auto_payment_link": True}
    first = post(client, "chat/", payload)
    assert first.status_code == 200, first.content
    assert first.json()["payment_cards"][0]["payment_key"] == "synthetic-key"
    assert post(client, "chat/", payload).json()["replayed"]
    assert upstream["calls"].count("BillsPayment") == 1
    assert run.call_count == 1
    upstream["paid"] = True
    post(client, "payment/", {"action": "status", "payment_key": "synthetic-key"})
    restored = client.get(f"/api/portal/history/{convo.pk}/").json()
    assert restored["payment_cards"][0]["payment_complete"] is True
    assert restored["payment_cards"][0]["redirect_url"] is None


def test_checkbox_false_disables_automatic_creation(browser_user, upstream, monkeypatch):
    client, user = browser_user
    op = saved_inquiry(user)
    monkeypatch.setattr(views, "run_turn", Mock(return_value={"ok": True, "tool_calls": trace(op)}))
    response = post(
        client,
        "chat/",
        {"message": "check bill", "client_key": str(uuid.uuid4()), "auto_payment_link": False},
    )
    assert response.status_code == 200
    assert not upstream["calls"]


def test_payment_keys_never_parse_model_text():
    assert not checkout.payment_keys({"reply": "https://bank.example/?key=not-a-tool-result"})
    assert checkout.payment_keys({"result": {"payment_key": "known"}}) == {"known"}


def test_fifty_turn_budget_is_shared_and_turn_fifty_one_is_blocked(browser_user, settings, monkeypatch):
    client, user = browser_user
    settings.AGENT_DAILY_MESSAGE_LIMIT = 50
    AgentDailyUsage.objects.create(usage_date=timezone.localdate(), messages_used=49)
    calls = []

    def reply(req):
        calls.append(req)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "synthetic"}}]}
        )

    monkeypatch.setattr(runner, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(reply)))
    r = post(client, "chat/", {"message": "fiftieth", "client_key": str(uuid.uuid4())})
    assert r.status_code == 200, r.content
    assert r.json()["agent_usage"]["remaining"] == 0
    r = post(client, "chat/", {"message": "fifty first", "client_key": str(uuid.uuid4())})
    assert r.json()["error"]["code"] == "agent_daily_limit"
    assert len(calls) == 1
    assert client.get("/api/portal/state/").json()["usage"]["limit"] == 50


def test_status_read_of_old_inquiry_never_creates_link(browser_user, upstream):
    _, user = browser_user
    old = trace(saved_inquiry(user))
    old[0]["name"] = "p24_operation_status"
    assert not checkout.prepare_inquiry_links(user, old)["entries"]
    assert not upstream["calls"]


def test_unexpected_link_error_preserves_query_and_stops(browser_user, monkeypatch):
    _, user = browser_user
    op = saved_inquiry(user)
    monkeypatch.setattr(checkout, "invoke", Mock(side_effect=RuntimeError("synthetic interruption")))
    result = checkout.prepare_inquiry_links(user, trace(op))
    assert result["notices"][0]["code"] == "AUTO_LINK_INTERRUPTED"
    op.refresh_from_db()
    assert op.status == "completed"


def test_model_loop_inquiry_auto_link_uses_only_one_turn(browser_user, upstream, monkeypatch, settings):
    client, user = browser_user
    settings.AGENT_DAILY_MESSAGE_LIMIT = 50
    settings.AGENT_MAX_STEPS = 3
    calls = []

    def model(req):
        payload = json.loads(req.content)
        calls.append(payload)
        if len(calls) == 1:
            name, arguments = "p24_mobile_bill", {"phone": "09120000000", "operator": "mci"}
        elif len(calls) == 2:
            prior = json.loads(payload["messages"][-1]["content"])
            name, arguments = "p24_run_inquiry", {"quote_id": prior["result"]["quote_id"]}
        else:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Inquiry done. See the structured card.",
                            }
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"synthetic-call-{len(calls)}",
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ],
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(runner, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(model)))
    result = post(client, "chat/", {"message": "Check mobile bill", "client_key": str(uuid.uuid4())})
    assert result.status_code == 200, result.content
    assert result.json()["payment_cards"][0]["total_amount"] == 92000
    assert len(calls) == 3
    assert AgentDailyUsage.objects.get().messages_used == 1
    assert upstream["calls"].count("CellPhoneBills") == 1
    assert upstream["calls"].count("BillsPayment") == 1
    assert not any(name in upstream["calls"] for name in ("WalletPayment", "CnpgPayment"))
