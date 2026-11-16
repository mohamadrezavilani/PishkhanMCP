"""Source-backed invoice transitions with mocked upstream wire calls.

These tests do not access production, send OTP or debit a real wallet.
"""

import json
from unittest.mock import Mock

import pytest

from apps.core import operations
from apps.core.errors import PishkhanError
from apps.core.models import AccountSession, Operation, Quote
from apps.providers.registry import find_action


@pytest.fixture
def live_session(db):
    return AccountSession.objects.create(mode="live", state="authenticated", token="fixture-session")


@pytest.fixture
def upstream(monkeypatch):
    responses = []
    calls = []

    def request(action, parameters, token):
        calls.append((action["group"], action["path"], parameters, token))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
        return {"status": {"Code": "G00000"}, "parameters": response}

    client = Mock()
    client.call.side_effect = request
    monkeypatch.setattr(operations, "PishkhanClient", lambda: client)
    return responses, calls


def invoice(*, key="purchase-fixture", amount=0, channels=None, summary=None, terms=""):
    return {
        "Invoice": {"PurchaseKey": key, "Amount": amount, "Service": {"Summary": summary}},
        "PaymentChannels": channels or [],
        "TermsAndConditions": terms,
    }


def prepare(session, request_key="prepare-fixture"):
    action = find_action("PostPackagesStatus", "services")
    return operations.prepare_inquiry(
        str(session.pk), action["id"], {"TrackingCode": "000123456789"}, request_key
    )


def test_configuration_message_preserves_quote_before_invoice(live_session, upstream):
    responses, calls = upstream
    responses.append({"Message": "اطلاعیهٔ خدمت"})
    result = prepare(live_session)
    assert result["status"] == "requires_user_action"
    quote = result["result"]
    assert quote["stage"] == "configuration_message"
    assert quote["amount"] is None
    assert [x[1] for x in calls] == ["v1/ConfigService"]

    # No acknowledgement makes no upstream request.
    still_pending = operations.resume_inquiry(str(live_session.pk), quote["quote_id"], "no-ack")
    assert still_pending["result"]["stage"] == "configuration_message"
    assert len(calls) == 1

    responses.append(invoice())
    resumed = operations.resume_inquiry(
        str(live_session.pk), quote["quote_id"], "ack", acknowledge_message=True
    )
    assert resumed["result"]["stage"] == "ready"
    assert calls[-1][1] == "v1/InvoiceRegister"
    wire = calls[-1][2]
    assert wire["Service"] == "v1_InquiryPostPackagesStatus"
    assert isinstance(wire["Parameters"], str)
    assert json.loads(wire["Parameters"]) == {"TrackingCode": "000123456789"}


def test_otp_without_purchase_key_resumes_same_quote(live_session, upstream):
    responses, calls = upstream
    responses.extend(
        [{}, {"Prerequisites": {"Type": "OTP", "Value": json.dumps({"Length": 6, "Timer": 120000})}}]
    )
    first = prepare(live_session)["result"]
    assert first["stage"] == "invoice_otp"
    assert first["prerequisite"]["data"]["Length"] == 6
    assert not Quote.objects.get(pk=first["quote_id"]).parameters.get("purchase_key")
    # Result retrieval does not bypass the missing service OTP.
    blocked = operations.run_inquiry(str(live_session.pk), first["quote_id"], "premature-run")
    assert blocked["stage"] == "invoice_otp"
    assert len(calls) == 2

    responses.append(invoice())
    resumed = operations.resume_inquiry(str(live_session.pk), first["quote_id"], "otp-submit", otp="۱۲۳۴۵۶")
    assert resumed["result"]["quote_id"] == first["quote_id"]
    assert resumed["result"]["stage"] == "ready"
    assert json.loads(calls[-1][2]["Parameters"]) == {"TrackingCode": "000123456789", "OTPCode": "123456"}
    assert "OTPCode" not in Quote.objects.get(pk=first["quote_id"]).parameters["input"]


def test_zero_fee_inquiry_has_no_payment_and_preserves_wire(live_session, upstream):
    responses, calls = upstream
    responses.extend([{}, invoice(), {"Result": {"Events": []}}])
    first = prepare(live_session)["result"]
    assert first["stage"] == "ready"
    result = operations.run_inquiry(str(live_session.pk), first["quote_id"], "run")
    assert result["status"] == "completed"
    assert calls[-1][1:3] == (
        "v1/PostPackagesStatus",
        {"TrackingCode": "000123456789", "PurchaseKey": "purchase-fixture"},
    )
    assert all("Payment" not in path for _, path, _, _ in calls)
    replay = operations.run_inquiry(str(live_session.pk), first["quote_id"], "different-key")
    assert replay["operation_id"] == result["operation_id"]
    assert replay["replayed"] is True
    assert len(calls) == 3


def test_preview_then_wallet_payment_cannot_skip_steps(live_session, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return?status=#status#"
    responses, calls = upstream
    channels = [{"Gateways": [{"Type": {"Name": "wallet-fixture"}}]}]
    responses.extend(
        [{}, invoice(amount=50000, channels=channels, summary=[{"Key": "موضوع", "Value": "مرسوله"}])]
    )
    first = prepare(live_session)["result"]
    assert first["stage"] == "invoice_preview"
    blocked = operations.pay_quote(
        str(live_session.pk), first["quote_id"], "wallet-fixture", False, "too-early"
    )
    assert blocked["stage"] == "invoice_preview"
    assert len(calls) == 2

    approved = operations.resume_inquiry(
        str(live_session.pk), first["quote_id"], "preview-ack", acknowledge_message=True
    )
    assert approved["result"]["stage"] == "payment_required"
    still_blocked = operations.run_inquiry(str(live_session.pk), first["quote_id"], "before-pay")
    assert still_blocked["stage"] == "payment_required"
    with pytest.raises(PishkhanError, match="درگاه"):
        operations.pay_quote(
            str(live_session.pk), first["quote_id"], "invented-gateway", False, "invalid-pay"
        )
    assert len(calls) == 2

    responses.extend([{"PaymentKey": "payment-fixture"}, {}, {"Status": {"Name": "Settle"}, "Bills": []}])
    paid = operations.pay_quote(str(live_session.pk), first["quote_id"], "wallet-fixture", False, "pay")
    assert paid["result"]["quote"]["stage"] == "ready"
    assert [x[1] for x in calls[-3:]] == ["v1/InvoicePayment", "v1/WalletPayment", "v1/PaymentInfo"]
    assert calls[-1][2] == {"PaymentKey": "payment-fixture"}
    again = operations.pay_quote(
        str(live_session.pk), first["quote_id"], "wallet-fixture", False, "other-pay-key"
    )
    assert again["stage"] == "ready"
    assert len(calls) == 5


def test_gateway_redirect_stays_pending_until_authoritative_result(live_session, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return?status=#status#"
    responses, calls = upstream
    channels = [{"Gateways": [{"Type": {"Name": "bank-fixture"}}]}]
    responses.extend(
        [
            {},
            invoice(amount=50000, channels=channels),
            {"PaymentKey": "payment-fixture", "RedirectLink": "https://gateway.example/pay"},
        ]
    )
    first = prepare(live_session)["result"]
    payment = operations.pay_quote(str(live_session.pk), first["quote_id"], "bank-fixture", False, "bank-pay")
    assert payment["status"] == "requires_user_action"
    assert payment["result"]["quote"]["stage"] == "payment_pending"
    assert not Quote.objects.get(pk=first["quote_id"]).parameters.get("payment_completed")

    responses.append(invoice(amount=50000, channels=channels))
    status = operations.invoice_status(str(live_session.pk), first["quote_id"])
    assert status["stage"] == "payment_pending"
    responses.append({"Result": {"Events": ["delivered"]}})
    result = operations.run_inquiry(str(live_session.pk), first["quote_id"], "after-gateway")
    assert result["status"] == "completed"
    assert calls[-1][1] == "v1/PostPackagesStatus"


def test_invoice_input_is_validated_before_any_upstream_request(live_session, upstream):
    _, calls = upstream
    action = find_action("ElectricBills", "services")
    with pytest.raises(PishkhanError) as error:
        operations.prepare_inquiry(str(live_session.pk), action["id"], {"wrong": "value"}, "bad-input")
    assert error.value.code == "INVALID_PARAMETERS"
    assert calls == []


def test_login_requires_device_session_before_sending_otp(db, upstream):
    _, calls = upstream
    session = AccountSession.objects.create(mode="live")
    result = operations.login(str(session.pk), "09000000000", idempotency_key="otp-without-session")
    assert result["ok"] is False
    assert result["result"]["error"]["code"] == "DEVICE_SESSION_REQUIRED"
    assert calls == []


def test_unexpected_exception_returns_durable_unknown_operation(live_session):
    def fail():
        raise RuntimeError("private-exception-argument")

    result = operations.execute_once(live_session, "fixture_action", {}, "unexpected-error", fail)
    assert result["ok"] is False
    assert result["status"] == Operation.Status.UNKNOWN
    assert result["operation_id"]
    assert "private-exception-argument" not in json.dumps(result)
    replay = operations.execute_once(live_session, "fixture_action", {}, "unexpected-error", fail)
    assert replay["replayed"] is True
    assert replay["operation_id"] == result["operation_id"]


def test_gateway_response_does_not_turn_rejected_result_into_success(live_session, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return?status=#status#"
    responses, calls = upstream
    channels = [{"Gateways": [{"Type": {"Name": "bank-fixture"}}]}]
    responses.extend(
        [
            {},
            invoice(amount=50000, channels=channels),
            {"PaymentKey": "payment-fixture", "RedirectLink": "https://gateway.example/pay"},
            PishkhanError("UPSTREAM_REJECTED", "هنوز پرداخت نشده است."),
        ]
    )
    first = prepare(live_session)["result"]
    operations.pay_quote(str(live_session.pk), first["quote_id"], "bank-fixture", False, "bank-start")
    result = operations.run_inquiry(str(live_session.pk), first["quote_id"], "premature-result")
    assert result["ok"] is False
    assert result["status"] == "failed"
    quote = Quote.objects.get(pk=first["quote_id"])
    assert quote.parameters["stage"] == "payment_pending"
    assert not quote.parameters.get("result_received")
    assert all(path != "v1/WalletPayment" for _, path, _, _ in calls)


def test_explicit_result_retry_recovers_after_gateway_rejection(live_session, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://callback.example/return?status=#status#"
    responses, calls = upstream
    channels = [{"Gateways": [{"Type": {"Name": "bank-fixture"}}]}]
    responses.extend(
        [
            {},
            invoice(amount=50000, channels=channels),
            {"PaymentKey": "payment-fixture", "RedirectLink": "https://gateway.example/pay"},
            PishkhanError("UPSTREAM_REJECTED", "هنوز پرداخت نشده است."),
        ]
    )
    quote_id = prepare(live_session)["result"]["quote_id"]
    operations.pay_quote(str(live_session.pk), quote_id, "bank-fixture", False, "pay-once")
    failed = operations.run_inquiry(str(live_session.pk), quote_id, "early-result")
    default_replay = operations.run_inquiry(str(live_session.pk), quote_id, "later-default")
    assert default_replay["operation_id"] == failed["operation_id"]
    assert len(calls) == 4

    responses.append({"Result": {"Events": ["delivered"]}})
    recovered = operations.run_inquiry(str(live_session.pk), quote_id, "after-payment", retry_failed=True)
    assert recovered["status"] == "completed"
    assert recovered["operation_id"] != failed["operation_id"]
    assert Operation.objects.get(pk=failed["operation_id"]).status == "failed"
    assert str(Quote.objects.get(pk=quote_id).operation_id) == recovered["operation_id"]
    assert calls[-1][1:3] == (
        "v1/PostPackagesStatus",
        {"TrackingCode": "000123456789", "PurchaseKey": "purchase-fixture"},
    )
    # Neither a normal fetch nor another explicit retry repeats a completed result.
    for retry in (False, True):
        replay = operations.run_inquiry(str(live_session.pk), quote_id, "another-key", retry_failed=retry)
        assert replay["operation_id"] == recovered["operation_id"]
        assert replay["replayed"] is True
    assert len(calls) == 5
    assert [path for _, path, _, _ in calls].count("v1/InvoiceRegister") == 1
    assert [path for _, path, _, _ in calls].count("v1/InvoicePayment") == 1


def test_same_failed_retry_key_replays_before_fresh_retry(live_session, upstream):
    responses, calls = upstream
    responses.extend([{}, invoice(), PishkhanError("UPSTREAM_REJECTED", "pending")])
    quote_id = prepare(live_session)["result"]["quote_id"]
    first = operations.run_inquiry(str(live_session.pk), quote_id, "initial")
    responses.append(PishkhanError("UPSTREAM_REJECTED", "still pending"))
    second = operations.run_inquiry(str(live_session.pk), quote_id, "retry-one", retry_failed=True)
    assert second["operation_id"] != first["operation_id"]
    repeated = operations.run_inquiry(str(live_session.pk), quote_id, "retry-one", retry_failed=True)
    assert repeated["operation_id"] == second["operation_id"]
    assert repeated["replayed"] is True
    assert len(calls) == 4
    responses.append({"Result": {"ready": True}})
    third = operations.run_inquiry(str(live_session.pk), quote_id, "retry-two", retry_failed=True)
    assert third["status"] == "completed"
    assert third["operation_id"] not in {first["operation_id"], second["operation_id"]}
    assert Operation.objects.filter(action_id="services_post_packages_status_v1").count() == 3


def test_unknown_result_is_never_retried(live_session, upstream):
    responses, calls = upstream
    responses.extend(
        [{}, invoice(), PishkhanError("UPSTREAM_TIMEOUT", "timeout", details={"outcome": "unknown"})]
    )
    quote_id = prepare(live_session)["result"]["quote_id"]
    first = operations.run_inquiry(str(live_session.pk), quote_id, "initial")
    assert first["status"] == "unknown"
    replay = operations.run_inquiry(str(live_session.pk), quote_id, "retry-unknown", retry_failed=True)
    assert replay["operation_id"] == first["operation_id"]
    assert replay["replayed"] is True
    assert len(calls) == 3
    assert Operation.objects.filter(action_id="services_post_packages_status_v1").count() == 1


def test_running_result_reservation_is_visible_before_upstream_response(live_session, upstream):
    responses, calls = upstream
    responses.extend([{}, invoice()])
    quote_id = prepare(live_session)["result"]["quote_id"]
    observed = []

    def inspect_while_upstream_running():
        observed.append(
            operations.run_inquiry(str(live_session.pk), quote_id, "competing-retry", retry_failed=True)
        )
        return {"Result": {"ready": True}}

    responses.append(inspect_while_upstream_running)
    completed = operations.run_inquiry(str(live_session.pk), quote_id, "initial")
    assert observed[0]["status"] == "running"
    assert observed[0]["replayed"] is True
    assert observed[0]["operation_id"] == completed["operation_id"]
    assert len(calls) == 3


def test_auth_retry_waits_for_reconnection_without_consuming_identity(live_session, upstream):
    responses, calls = upstream
    responses.extend([{}, invoice(), PishkhanError("AUTH_REQUIRED", "expired")])
    quote_id = prepare(live_session)["result"]["quote_id"]
    failed = operations.run_inquiry(str(live_session.pk), quote_id, "initial")
    with pytest.raises(PishkhanError) as error:
        operations.run_inquiry(str(live_session.pk), quote_id, "reconnect-retry", retry_failed=True)
    assert error.value.code == "DEVICE_SESSION_REQUIRED"
    assert str(Quote.objects.get(pk=quote_id).operation_id) == failed["operation_id"]
    assert len(calls) == 3
    live_session.refresh_from_db()
    live_session.token = "new-fixture-session"
    live_session.state = "authenticated"
    live_session.save()
    responses.append({"Result": {"ready": True}})
    recovered = operations.run_inquiry(str(live_session.pk), quote_id, "reconnect-retry", retry_failed=True)
    assert recovered["status"] == "completed"
    assert calls[-1][3] == "new-fixture-session"


def test_retry_does_not_start_an_unattempted_inquiry(live_session, upstream):
    responses, calls = upstream
    responses.extend([{}, invoice()])
    quote_id = prepare(live_session)["result"]["quote_id"]
    with pytest.raises(PishkhanError) as error:
        operations.run_inquiry(str(live_session.pk), quote_id, "not-a-retry", retry_failed=True)
    assert error.value.code == "INQUIRY_NOT_RETRYABLE"
    assert len(calls) == 2
