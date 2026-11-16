"""Callback contract/recovery tests. Synthetic data; no bank/model requests."""

import hashlib
import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.db.models.query import QuerySet
from django.utils import timezone

from apps.core import operations, payments
from apps.core.errors import PishkhanError
from apps.core.models import AccountSession, Operation, PaymentAttempt, ProviderCall, Quote, UserRequest
from apps.core.tools import call_tool

pytestmark = pytest.mark.django_db
GATEWAY = "OnlinePayment_Test"
SERVICE = "v1_InquiryCellPhoneBills"
BILL = "synthetic-mobile-bill"
KEY = "bills:" + hashlib.sha256(json.dumps([BILL]).encode()).hexdigest()
WIRE = {"Bills": [BILL], "Gateway": GATEWAY, "Service": SERVICE}


@pytest.fixture
def account(settings):
    settings.P24_PAYMENT_CALLBACK = ""
    return AccountSession.objects.create(mode="live", state="authenticated", token="synthetic-session")


@pytest.fixture
def upstream(monkeypatch):
    calls = []

    def invoke(action, parameters, token):
        calls.append((action["path"], parameters))
        if action["path"] == "v1/BillsPaymentChannels":
            data = {"PaymentChannels": [{"Gateways": [{"Type": {"Name": GATEWAY}}]}]}
        elif action["path"] in {"v1/BillsPayment", "v1/InvoicePayment"}:
            data = {"PaymentKey": "synthetic-payment", "RedirectLink": "https://gateway.example/pay"}
        else:
            raise AssertionError("Unexpected upstream call")
        return {"status": {"Code": "G00000"}, "parameters": data}

    client = Mock()
    client.call.side_effect = invoke
    monkeypatch.setattr(operations, "PishkhanClient", lambda: client)
    return calls


def prepare(account, **extra):
    return call_tool(
        "p24_prepare_bill_payment",
        {
            "session_id": str(account.pk),
            "bill_ids": [BILL],
            "gateway": GATEWAY,
            "service_name": SERVICE,
            "idempotency_key": "client-key",
            **extra,
        },
    )


def legacy_failure(account, *, code="CALLBACK_NOT_CONFIGURED", status=Operation.Status.FAILED):
    def fail():
        raise PishkhanError(code, "Synthetic previous local error")

    result = operations.execute_once(account, "bill_payment", WIRE, KEY, fail, service_id="mci")
    op = Operation.objects.get(pk=result["operation_id"])
    if status != op.status:
        op.status = status
        op.save(update_fields=["status"])
    return op


@pytest.mark.parametrize("callback", ["", "   "])
def test_empty_callback_uses_native_core_return(account, upstream, settings, callback):
    settings.P24_PAYMENT_CALLBACK = callback
    result = prepare(account)
    assert result["ok"]
    assert result["status"] == "requires_user_action"
    assert result["result"]["callback_mode"] == "core_default"
    assert result["result"]["payment_flow"] == "ipg"
    assert result["result"]["parameters"]["RedirectLink"] == "https://gateway.example/pay"
    assert result["result"]["financial_state"] == "unknown"
    assert upstream == [
        ("v1/BillsPaymentChannels", {"Service": SERVICE, "Bills": [BILL]}),
        ("v1/BillsPayment", {"Callback": "", "Gateway": GATEWAY, "Bills": [BILL]}),
    ]
    assert PaymentAttempt.objects.get().payment_key == "synthetic-payment"
    again = prepare(account, idempotency_key="new-model-key")
    assert again["operation_id"] == result["operation_id"]
    assert again["replayed"]
    assert len(upstream) == 2


def test_custom_callback_is_forwarded_not_replaced(account, upstream, settings):
    settings.P24_PAYMENT_CALLBACK = "https://approved.example/payments/return/"
    result = prepare(account)
    assert result["result"]["callback_mode"] == "custom"
    assert upstream[-1][1]["Callback"] == settings.P24_PAYMENT_CALLBACK


def test_empty_callback_also_supported_for_invoice_payment(account, upstream):
    req = UserRequest.objects.create(session=account, client_key="parcel", service_id="posttracking")
    quote = Quote.objects.create(
        session=account,
        request=req,
        service_id="posttracking",
        action_id="services_post_packages_status_v1",
        expires_at=timezone.now() + timedelta(minutes=10),
        parameters={
            "stage": "payment_required",
            "purchase_key": "synthetic-invoice",
            "invoice": {"PaymentChannels": [{"Gateways": [{"Type": {"Name": GATEWAY}}]}]},
        },
    )
    result = payments.pay_quote(str(account.pk), str(quote.pk), GATEWAY, False, "pay-quote")
    assert result["ok"] and result["status"] == "requires_user_action"
    assert upstream[0][0] == "v1/InvoicePayment"
    assert upstream[0][1]["Callback"] == ""
    assert result["request_id"] == str(req.pk)
    assert result["result"]["callback_mode"] == "core_default"


def test_legacy_local_callback_error_resumes_same_reservation_once(account, upstream):
    old = legacy_failure(account)
    before = old.created_at
    result = prepare(account, request_id=str(old.request_id), idempotency_key="different-model-key")
    assert result["ok"]
    assert result["operation_id"] == str(old.pk)
    assert result["request_id"] == str(old.request_id)
    old.refresh_from_db()
    assert old.created_at == before
    assert old.status == "requires_user_action"
    assert Operation.objects.count() == 1
    assert old.calls.count() == 2
    replay = prepare(account, idempotency_key="yet-another-key")
    assert replay["replayed"] and len(upstream) == 2


@pytest.mark.parametrize("evidence", ["provider_call", "payment_attempt", "upstream_reference"])
def test_legacy_error_with_any_upstream_evidence_is_not_replayed(account, upstream, evidence):
    op = legacy_failure(account)
    if evidence == "provider_call":
        ProviderCall.objects.create(session=account, operation=op, action_id="core_bills_payment_v1")
    elif evidence == "payment_attempt":
        PaymentAttempt.objects.create(session=account, operation=op, payment_key="existing-key")
    else:
        op.upstream_reference = "existing-reference"
        op.save(update_fields=["upstream_reference"])
    result = prepare(account)
    assert not result["ok"] and result["replayed"]
    assert not upstream


@pytest.mark.parametrize("status", ["running", "unknown", "pending", "completed", "requires_user_action"])
def test_non_failed_callback_reservations_are_never_reclaimed(account, upstream, status):
    legacy_failure(account, status=status)
    result = prepare(account)
    assert result["status"] == status and result["replayed"]
    assert not upstream


def test_other_failed_payment_is_not_automatically_retried(account, upstream):
    legacy_failure(account, code="UPSTREAM_TIMEOUT")
    result = prepare(account)
    assert result["replayed"] and not result["ok"]
    assert not upstream


def test_legacy_callback_error_cannot_be_attached_to_different_behavior(account, upstream):
    legacy_failure(account)
    other = UserRequest.objects.create(session=account, client_key="different-request", service_id="mci")
    result = prepare(account, request_id=str(other.pk))
    assert result["error"]["code"] == "REQUEST_MISMATCH"
    assert not upstream


def test_legacy_callback_recovery_preserves_input_fingerprint(account, upstream):
    op = legacy_failure(account)
    result = prepare(account, gateway="OtherGateway")
    assert result["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    op.refresh_from_db()
    assert op.status == "failed" and not upstream


def test_losing_callback_recovery_claim_does_not_contact_core(account, upstream, monkeypatch):
    op = legacy_failure(account)
    original_update = QuerySet.update

    def competing_update(queryset, **values):
        if queryset.model is Operation and values.get("status") == Operation.Status.RUNNING:
            original_update(Operation.objects.filter(pk=op.pk), status=Operation.Status.RUNNING)
            return original_update(queryset, **values)
        return original_update(queryset, **values)

    monkeypatch.setattr(QuerySet, "update", competing_update)
    result = prepare(account)
    assert result["replayed"] and result["status"] == "running"
    assert not upstream


def test_uncertain_result_after_recovery_is_not_repeated(account, upstream, monkeypatch):
    op = legacy_failure(account)
    original = operations.live_call

    def timeout_after_channel(session, action, parameters):
        if action["path"] == "v1/BillsPayment":
            raise PishkhanError("UPSTREAM_TIMEOUT", "Unknown", details={"outcome": "unknown"})
        return original(session, action, parameters)

    monkeypatch.setattr(operations, "live_call", timeout_after_channel)
    result = prepare(account)
    assert result["operation_id"] == str(op.pk) and result["status"] == "unknown"
    replay = prepare(account)
    assert replay["replayed"] and replay["status"] == "unknown"
    assert len(upstream) == 1
