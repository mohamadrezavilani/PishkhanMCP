"""Ghabzino IPG completion regressions; synthetic payloads, no bank/model calls."""

from unittest.mock import Mock

import pytest

from apps.core import operations
from apps.core.models import AccountSession, Operation, PaymentAttempt, UserRequest
from apps.core.tools import call_tool

pytestmark = pytest.mark.django_db


@pytest.fixture
def payment(monkeypatch):
    session = AccountSession.objects.create(mode="live", state="authenticated", token="synthetic")
    request = UserRequest.objects.create(session=session, client_key="paid-check", service_id="mci")
    op = Operation.objects.create(
        session=session,
        request=request,
        action_id="bill_payment",
        idempotency_key="synthetic-bills",
        request_hash="synthetic",
        status="requires_user_action",
        result={"requires_user_action": True, "next_step": "Complete RedirectLink"},
    )
    attempt = PaymentAttempt.objects.create(
        session=session,
        request=request,
        operation=op,
        payment_key="synthetic-payment",
        gateway="OnlinePayment_Sadad_Ghabzino",
        bill_ids=["bill-one"],
    )
    provider = Mock()
    provider.call.return_value = {
        "status": {"Code": "G00000"},
        "parameters": {
            "Status": {"Name": "Paid"},
            "Amount": 12300,
            "Fee": 0,
            "TotalAmount": 12300,
            "ExtraInfo": {"TraceNumber": None, "TransactionUniqueID": None, "SettlementCertificateUrl": None},
            "Bills": [{"UniqueID": "bill-one", "Payment": {"Status": {"Name": "Paid"}}}],
        },
    }
    monkeypatch.setattr(operations, "PishkhanClient", lambda: provider)
    return session, attempt, op, provider


def read_status(payment):
    session, attempt, _, _ = payment
    return call_tool(
        "p24_payment_status", {"session_id": str(session.pk), "payment_key": attempt.payment_key}
    )


def test_paid_ghabzino_bill_finishes_payment_without_fabricating_settle(payment):
    result = read_status(payment)
    assert result["pending"] is False
    assert result["financial_state"] == "paid"
    assert result["payment_complete"] is True
    assert result["payment_confirmed"] is True
    assert result["all_bills_payment_confirmed"] is True
    assert result["all_bills_settlement_reported"] is False
    assert result["settled"] is False
    assert result["payment_status"] == result["bill_statuses"][0]["status"] == "Paid"
    assert result["transaction_details"]["TraceNumber"] is None
    assert result["requires_user_action"] is False
    op = payment[2]
    op.refresh_from_db()
    assert op.status == "completed"
    assert op.result["requires_user_action"] is False
    assert op.result["next_step"] == "none"
    assert [args.args[0]["path"] for args in payment[3].call.call_args_list] == ["v1/PaymentInfo"]


@pytest.mark.parametrize("gateway", ["OnlinePayment_AP_Ghabzino", "OnlinePayment_Sadad_Ghabzino"])
def test_repeated_read_never_creates_or_pays_again(payment, gateway):
    payment[1].gateway = gateway
    payment[1].save(update_fields=["gateway"])
    first, second = read_status(payment), read_status(payment)
    assert first["payment_complete"] and second["payment_complete"]
    assert Operation.objects.count() == PaymentAttempt.objects.count() == 1
    assert first["request_id"] == second["request_id"] == str(payment[1].request_id)
    assert all(c.args[0]["path"] == "v1/PaymentInfo" for c in payment[3].call.call_args_list)


@pytest.mark.parametrize("bill_status", ["Unpaid", "Unknown", "InProcess", "Return", "Unpayable"])
def test_one_successful_bill_does_not_complete_a_mixed_payment(payment, bill_status):
    attempt, provider = payment[1], payment[3]
    attempt.bill_ids = ["bill-one", "bill-two"]
    attempt.save(update_fields=["bill_ids"])
    provider.call.return_value["parameters"]["Bills"].append(
        {"UniqueID": "bill-two", "Payment": {"Status": {"Name": bill_status}}}
    )
    result = read_status(payment)
    assert result["payment_confirmed"] is True
    assert result["payment_complete"] is False
    assert result["all_bills_payment_confirmed"] is False
    assert result["pending"] is True
    assert result["requires_user_action"] is False
    assert Operation.objects.get(pk=payment[2].pk).status == "pending"


@pytest.mark.parametrize(
    "bills", [None, [], [{"UniqueID": "different", "Payment": {"Status": {"Name": "Paid"}}}]]
)
def test_missing_expected_bill_is_not_completion(payment, bills):
    payment[3].call.return_value["parameters"]["Bills"] = bills
    result = read_status(payment)
    assert not result["payment_complete"]
    assert result["pending"]


def test_conflicting_duplicate_bill_status_is_not_completion(payment):
    payment[3].call.return_value["parameters"]["Bills"].append(
        {"UniqueID": "bill-one", "Payment": {"Status": {"Name": "Unpaid"}}}
    )
    assert not read_status(payment)["payment_complete"]


def test_only_an_explicit_settle_reports_settlement(payment):
    data = payment[3].call.return_value["parameters"]
    data["Status"]["Name"] = "Settle"
    data["Bills"][0]["Payment"]["Status"]["Name"] = "Settle"
    result = read_status(payment)
    assert result["settled"] and result["all_bills_settlement_reported"]
    assert result["payment_complete"] and not result["pending"]


def test_payment_settle_does_not_hide_an_unpaid_bill(payment):
    data = payment[3].call.return_value["parameters"]
    data["Status"]["Name"] = "Settle"
    data["Bills"][0]["Payment"]["Status"]["Name"] = "Unpaid"
    result = read_status(payment)
    assert result["settled"]  # Raw payment-level observation, not all bills.
    assert not result["payment_complete"] and result["pending"]
    assert not result["all_bills_payment_confirmed"]


def test_unknown_gateway_does_not_inherit_ghabzino_completion_rule(payment):
    payment[1].gateway = "OnlinePayment_Unreviewed"
    payment[1].save(update_fields=["gateway"])
    assert not read_status(payment)["payment_complete"]


def test_missing_subject_does_not_inherit_bill_completion_rule(payment):
    payment[1].bill_ids = []
    payment[1].save(update_fields=["bill_ids"])
    result = read_status(payment)
    assert result["all_bills_payment_confirmed"] is None
    assert not result["payment_complete"]


@pytest.mark.parametrize("status", ["Unpaid", "Unknown", "InProcess", "Return", "Unpayable"])
def test_bill_paid_does_not_override_unsuccessful_payment_status(payment, status):
    payment[3].call.return_value["parameters"]["Status"]["Name"] = status
    assert not read_status(payment)["payment_complete"]
