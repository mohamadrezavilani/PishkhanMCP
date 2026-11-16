"""Domain workflows through the same public tools used by MCP and the agent."""

import json
from datetime import timedelta
from unittest.mock import Mock

import httpx
import pytest
from django.utils import timezone

from apps.core import operations
from apps.core.models import AccountSession, Operation, Quote
from apps.core.tools import call_tool
from apps.providers.client import PishkhanClient


@pytest.fixture
def account(db, settings):
    settings.P24_MODE = "demo"
    result = call_tool("p24_create_session", {})
    assert result["ok"] and result["mode"] == "demo"
    return AccountSession.objects.get(pk=result["session_id"])


def invoke(account, name, **arguments):
    return call_tool(name, {"session_id": str(account.pk), **arguments})


def test_capabilities_executes_and_distinguishes_catalog_from_live_coverage(settings):
    settings.P24_MODE = "demo"
    result = call_tool("p24_capabilities", {})
    assert result["ok"]
    assert result["catalog_service_count"] == 55
    assert result["demo_services"] == ["electricity", "freeway", "posttracking", "water"]
    assert result["provider"]["source_verified_actions"] > 0
    assert result["provider"]["authenticated_live_validation"] is False


def test_demo_otp_lifecycle_and_invalid_code(account):
    pending = invoke(account, "p24_request_otp", phone="۰۹۱۲۱۲۳۴۵۶۷", idempotency_key="request-otp")
    assert pending["ok"] and pending["status"] == "completed"
    account.refresh_from_db()
    assert account.phone == "09121234567"
    assert account.state == "otp_pending"
    failed = invoke(account, "p24_verify_otp", phone=account.phone, otp="111111", idempotency_key="wrong-otp")
    assert not failed["ok"]
    assert failed["status"] == "failed"
    assert failed["result"]["error"]["code"] == "INVALID_OTP"
    account.refresh_from_db()
    assert account.state == "otp_pending"
    accepted = invoke(
        account, "p24_verify_otp", phone=account.phone, otp="۱۲۳۴۵۶", idempotency_key="right-otp"
    )
    assert accepted["ok"]
    account.refresh_from_db()
    assert account.state == "authenticated"
    stored = Operation.objects.get(pk=accepted["operation_id"])
    assert stored.request_data["OTPCode"] == "[redacted]"


def test_password_login_does_not_persist_raw_password(account):
    result = invoke(
        account,
        "p24_login_password",
        phone="09121234567",
        password="example-only-password",
        idempotency_key="password-login",
    )
    assert result["ok"]
    account.refresh_from_db()
    assert account.state == "authenticated"
    stored = Operation.objects.get(pk=result["operation_id"])
    assert stored.request_data["Password"] == "[redacted]"
    assert "example-only-password" not in json.dumps(result)


def test_inquiry_replay_is_same_operation_and_different_input_is_rejected(account):
    first = invoke(account, "p24_electricity_bill", bill_id="۰۰۰۱۲۳۴۵", idempotency_key="bill-lookup")
    replay = invoke(account, "p24_electricity_bill", bill_id="00012345", idempotency_key="bill-lookup")
    assert first["ok"] and replay["ok"]
    assert first["operation_id"] == replay["operation_id"]
    assert replay["replayed"]
    assert first["result"]["data"]["bill_id"] == "00012345"
    assert Operation.objects.filter(session=account).count() == 1
    mismatch = invoke(account, "p24_electricity_bill", bill_id="999999", idempotency_key="bill-lookup")
    assert not mismatch["ok"]
    assert mismatch["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert Operation.objects.filter(session=account).count() == 1


def test_demo_bill_payment_requires_explicit_simulation_before_receipt(account):
    result = invoke(
        account,
        "p24_prepare_bill_payment",
        bill_ids=["demo-bill"],
        gateway="demo",
        idempotency_key="prepare-bill",
    )
    assert result["ok"] and result["status"] == "requires_user_action"
    receipt = invoke(account, "p24_get_receipt", operation_id=result["operation_id"])
    assert receipt["receipt_available"] is False
    completed = invoke(account, "p24_demo_complete_payment", operation_id=result["operation_id"])
    assert completed["ok"] and completed["status"] == "completed"
    receipt = invoke(account, "p24_get_receipt", operation_id=result["operation_id"])
    assert receipt["receipt_available"]
    assert receipt["receipt"]["real_money_moved"] is False
    assert receipt["receipt"]["reference"].startswith("DEMO-")


def test_paid_parcel_quote_executes_once_even_with_new_caller_key(account):
    proposed = invoke(
        account, "p24_quote_parcel_inquiry", tracking_code="000123456789", idempotency_key="parcel-quote"
    )
    assert proposed["ok"]
    quote_id = proposed["result"]["quote_id"]
    quote = Quote.objects.get(pk=quote_id)
    assert quote.amount is not None and quote.amount > 0
    first = invoke(account, "p24_run_parcel_inquiry", quote_id=quote_id, idempotency_key="parcel-run")
    count = Operation.objects.filter(session=account).count()
    replay = invoke(
        account, "p24_run_parcel_inquiry", quote_id=quote_id, idempotency_key="different-caller-key"
    )
    assert first["ok"] and replay["ok"]
    assert first["operation_id"] == replay["operation_id"]
    assert Operation.objects.filter(session=account).count() == count
    assert first["result"]["demo"]


def test_expired_parcel_quote_cannot_start_new_execution(account):
    result = invoke(
        account, "p24_quote_parcel_inquiry", tracking_code="123456", idempotency_key="expire-quote"
    )
    quote_id = result["result"]["quote_id"]
    Quote.objects.filter(pk=quote_id).update(expires_at=timezone.now() - timedelta(seconds=1))
    executed = invoke(account, "p24_run_parcel_inquiry", quote_id=quote_id, idempotency_key="expired-run")
    assert not executed["ok"]
    assert executed["error"]["code"] == "QUOTE_EXPIRED"


def test_operations_quotes_and_saved_items_are_scoped_to_session(account):
    other = AccountSession.objects.create(mode="demo")
    result = invoke(account, "p24_toll_summary", plate="12الف34567", idempotency_key="owner-toll")
    denied = invoke(other, "p24_get_transaction", operation_id=result["operation_id"])
    assert not denied["ok"] and denied["error"]["code"] == "OPERATION_NOT_FOUND"
    quote = invoke(account, "p24_quote_parcel_inquiry", tracking_code="123456", idempotency_key="owner-quote")
    denied = invoke(
        other, "p24_run_parcel_inquiry", quote_id=quote["result"]["quote_id"], idempotency_key="other-run"
    )
    assert not denied["ok"] and denied["error"]["code"] == "QUOTE_NOT_FOUND"
    saved = invoke(
        account, "p24_save_item", service_id="electricity", label="خانه", data={"bill_id": "000123"}
    )
    assert saved["ok"]
    assert len(invoke(account, "p24_list_saved_items")["items"]) == 1
    assert invoke(other, "p24_list_saved_items")["items"] == []


def test_closed_session_rejects_operations(account):
    assert invoke(account, "p24_close_session")["ok"]
    account.refresh_from_db()
    assert account.state == "closed" and account.token == "" and account.device_session == ""
    result = invoke(account, "p24_wallet_balance")
    assert not result["ok"]
    assert result["error"]["code"] == "SESSION_CLOSED"


def test_upstream_timeout_is_unknown_and_never_automatically_repeated(account):
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("simulated timeout", request=request)

    client = PishkhanClient(transport=httpx.MockTransport(timeout))

    def execute():
        return client.call({"group": "core", "path": "/UserWallets"}, {}, "test-session")

    first = operations.execute_once(account, "test-wallet-timeout", {}, "same-timeout-key", execute)
    assert not first["ok"] and first["status"] == "unknown"
    assert first["result"]["error"]["code"] == "UPSTREAM_TIMEOUT"
    replay = operations.execute_once(account, "test-wallet-timeout", {}, "same-timeout-key", execute)
    assert replay["operation_id"] == first["operation_id"]
    assert not replay["ok"] and replay["replayed"]
    assert len(calls) == 1


def test_unexpected_executor_error_returns_persisted_unknown_operation(account, monkeypatch):
    failure = Mock(side_effect=RuntimeError("provider-crashed-with-private-details"))
    monkeypatch.setattr("apps.providers.demo.inquiry", failure)
    result = invoke(account, "p24_electricity_bill", bill_id="1234", idempotency_key="executor-error")
    assert not result["ok"]
    assert result["status"] == "unknown"
    assert result["operation_id"]
    assert "provider-crashed-with-private-details" not in json.dumps(result)
    assert Operation.objects.get(pk=result["operation_id"]).status == "unknown"
    replay = invoke(account, "p24_electricity_bill", bill_id="1234", idempotency_key="executor-error")
    assert replay["operation_id"] == result["operation_id"]
    assert failure.call_count == 1


def test_non_dictionary_provider_result_has_no_receipt_instead_of_crashing(account):
    operation = Operation.objects.create(
        session=account,
        service_id="",
        action_id="history",
        idempotency_key="list-result",
        request_hash="0" * 64,
        status="completed",
        result={"parameters": []},
    )
    result = invoke(account, "p24_get_receipt", operation_id=str(operation.pk))
    assert result["ok"]
    assert result["receipt_available"] is False


def test_invalid_inputs_are_structured_and_do_not_create_operations(account):
    before = Operation.objects.count()
    invalid = invoke(account, "p24_electricity_bill", bill_id=1234, idempotency_key="invalid-number")
    assert not invalid["ok"] and invalid["error"]["code"] == "INVALID_ARGUMENTS"
    unknown = call_tool("p24_service_requirements", {"service_id": "not-real"})
    assert not unknown["ok"] and unknown["error"]["code"] == "UNKNOWN_SERVICE"
    assert Operation.objects.count() == before


def test_receipt_mode_follows_existing_session_when_default_changes(account, settings):
    payment = invoke(
        account,
        "p24_prepare_bill_payment",
        bill_ids=["demo-bill"],
        gateway="demo",
        idempotency_key="mode-payment",
    )
    invoke(account, "p24_demo_complete_payment", operation_id=payment["operation_id"])
    settings.P24_MODE = "live"
    receipt = invoke(account, "p24_get_receipt", operation_id=payment["operation_id"])
    assert receipt["ok"]
    assert receipt["mode"] == "demo"
    assert receipt["receipt"]["real_money_moved"] is False
