"""LAN pilot regressions: synthetic sessions, model responses and financial data."""

import json
import uuid
from datetime import timedelta
from unittest.mock import Mock

import httpx
import pytest
from django.test import Client
from django.utils import timezone

from apps.agent import runner
from apps.core.models import AccountSession, AgentDailyUsage, Conversation, Operation, PaymentAttempt
from apps.portal import services, views
from apps.portal.boundary import LANBoundary
from apps.portal.models import ChatTurn, Feedback, PaymentSnapshot, Visitor

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def settings_for_pilot(settings):
    settings.P24_MODE = "demo"
    settings.P24_ACCESS_KEY = ""
    settings.AGENT_BASE_URL = "https://model.example/v1"
    settings.AGENT_MODEL = "synthetic"
    settings.AGENT_MAX_STEPS = 3
    settings.AGENT_MAX_OUTPUT_TOKENS = 1200
    settings.AGENT_DAILY_MESSAGE_LIMIT = 10


def post(client, path, payload):
    csrf = client.cookies.get("csrftoken")
    return client.post(
        "/api/portal/" + path,
        data=json.dumps(payload),
        content_type="application/json",
        **({"HTTP_X_CSRFTOKEN": csrf.value} if csrf else {}),
    )


def login(client, phone="09120000000"):
    client.get("/")
    assert post(client, "otp/send/", {"phone": phone}).status_code == 200
    result = post(client, "otp/verify/", {"otp": "123456"})
    assert result.status_code == 200, result.content
    return Visitor.objects.get(pk=client.session["portal_visitor"])


@pytest.fixture
def browser():
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def user(browser):
    return login(browser)


def test_home_has_consumer_ui_not_raw_console(browser):
    response = browser.get("/")
    assert response.status_code == 200
    assert b"chat-form" in response.content
    assert b"session-id" not in response.content
    assert b"execute-tool" not in response.content
    assert browser.cookies.get("csrftoken")


def test_assets_work_without_debug(browser, settings):
    settings.DEBUG = False
    assert browser.get("/portal-assets/pilot.css").status_code == 200
    assert browser.get("/portal-assets/pilot.js").status_code == 200
    assert browser.get("/portal-assets/settings.py").status_code == 404


def test_initial_get_does_not_create_core_account(browser, monkeypatch):
    call = Mock()
    monkeypatch.setattr(views, "call_tool", call)
    result = browser.get("/api/portal/state/").json()
    assert not result["authenticated"]
    assert not AccountSession.objects.exists()
    call.assert_not_called()


def test_otp_login_requires_csrf(browser):
    browser.get("/")
    r = browser.post(
        "/api/portal/otp/send/", data=json.dumps({"phone": "09120000000"}), content_type="application/json"
    )
    assert r.status_code == 403
    assert not AccountSession.objects.exists()


def test_persian_phone_and_otp_are_normalized(browser):
    browser.get("/")
    phone = "\u06f0\u06f9\u06f1\u06f2\u06f0\u06f0\u06f0\u06f0\u06f0\u06f0\u06f0"
    sent = post(browser, "otp/send/", {"phone": phone})
    assert sent.status_code == 200
    assert sent.json()["phone"] == "09120000000"
    verified = post(browser, "otp/verify/", {"otp": "\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6"})
    assert verified.status_code == 200
    assert verified.json()["authenticated"] is True
    assert "session_id" not in verified.json()


def test_separate_browsers_have_distinct_accounts_and_history(browser, user):
    other = Client(enforce_csrf_checks=True)
    another = login(other, "09120000001")
    assert another.account_id != user.account_id
    conversation = Conversation.objects.create(
        session=user.account, messages=[{"role": "user", "content": "private conversation"}]
    )
    assert len(browser.get("/api/portal/state/").json()["conversations"]) == 1
    assert other.get("/api/portal/state/").json()["conversations"] == []
    assert other.get(f"/api/portal/history/{conversation.pk}/").status_code == 404
    assert browser.get(f"/api/portal/history/{conversation.pk}/").status_code == 200


@pytest.mark.parametrize("field", ["session_id", "account_id", "visitor_id"])
def test_client_cannot_select_another_account(browser, user, field):
    r = post(browser, "chat/", {"message": "test", "client_key": str(uuid.uuid4()), field: str(uuid.uuid4())})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BROWSER_SESSION_REQUIRED"


def test_otp_resend_cooldown_and_mode(browser):
    browser.get("/")
    first = post(browser, "otp/send/", {"phone": "09120000000"})
    assert first.status_code == 200 and first.json()["mode"] == "demo"
    assert post(browser, "otp/send/", {"phone": "09120000000"}).status_code == 429
    Visitor.objects.update(otp_sent_at=timezone.now() - timedelta(seconds=61))
    assert post(browser, "otp/send/", {"phone": "09120000000"}).status_code == 200


def test_otp_verification_needs_request(browser):
    browser.get("/")
    assert post(browser, "otp/verify/", {"otp": "123456"}).json()["error"]["code"] == "OTP_NOT_REQUESTED"


def test_authenticated_account_cannot_rebind_before_logout(browser, user):
    assert post(browser, "otp/send/", {"phone": "09120000001"}).status_code == 409
    assert post(browser, "logout/", {}).status_code == 200
    user.account.refresh_from_db()
    assert user.account.state == "closed"
    assert browser.get("/api/portal/state/").json()["authenticated"] is False


def test_old_developer_accounts_are_not_adopted(browser):
    old = AccountSession.objects.create(mode="live", state="authenticated", token="legacy-token")
    visitor = login(browser)
    assert visitor.account_id != old.pk
    assert "legacy-token" not in browser.get("/api/portal/state/").content.decode()


def test_chat_replay_does_not_call_model_twice(browser, user, monkeypatch):
    convo = Conversation.objects.create(session=user.account)
    run = Mock(
        return_value={"ok": True, "reply": "hello", "conversation_id": str(convo.pk), "tool_calls": []}
    )
    monkeypatch.setattr(views, "run_turn", run)
    payload = {"message": "hello", "client_key": str(uuid.uuid4())}
    first = post(browser, "chat/", payload)
    second = post(browser, "chat/", payload)
    assert first.status_code == second.status_code == 200
    assert second.json()["replayed"]
    assert run.call_count == 1
    assert run.call_args.kwargs["tool_names"] == services.PILOT_TOOLS
    assert post(browser, "chat/", {**payload, "message": "other"}).status_code == 409


def test_running_turn_blocks_parallel_chat_logout_and_payment(browser, user, monkeypatch):
    Visitor.objects.filter(pk=user.pk).update(active_turn=str(uuid.uuid4()))
    run = Mock()
    monkeypatch.setattr(views, "run_turn", run)
    assert post(browser, "chat/", {"message": "hi", "client_key": str(uuid.uuid4())}).status_code == 409
    assert post(browser, "payment/", {"action": "status", "payment_key": "other"}).status_code == 409
    assert post(browser, "logout/", {}).status_code == 409
    run.assert_not_called()


def test_model_exception_is_unknown_not_retried(browser, user, monkeypatch):
    run = Mock(side_effect=RuntimeError("do not disclose credentials"))
    monkeypatch.setattr(views, "run_turn", run)
    payload = {"message": "hi", "client_key": str(uuid.uuid4())}
    response = post(browser, "chat/", payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TURN_INTERRUPTED"
    assert "credentials" not in response.content.decode()
    assert ChatTurn.objects.get(visitor=user).state == "unknown"
    assert post(browser, "chat/", payload).json()["replayed"]
    assert run.call_count == 1
    user.refresh_from_db()
    assert not user.active_turn


def test_recovery_status_is_scoped(browser, user):
    turn = ChatTurn.objects.create(
        visitor=user, client_key=uuid.uuid4(), fingerprint="f", state="completed", response={"ok": True}
    )
    assert browser.get(f"/api/portal/turns/{turn.client_key}/").json()["state"] == "completed"
    other = Client()
    assert other.get(f"/api/portal/turns/{turn.client_key}/").status_code == 404


def test_foreign_conversation_rejected_before_model(browser, user, monkeypatch):
    other = AccountSession.objects.create()
    convo = Conversation.objects.create(session=other)
    run = Mock()
    monkeypatch.setattr(views, "run_turn", run)
    response = post(
        browser,
        "chat/",
        {"message": "test", "client_key": str(uuid.uuid4()), "conversation_id": str(convo.pk)},
    )
    assert response.status_code == 404
    run.assert_not_called()


@pytest.mark.parametrize(
    "action,payload",
    [("link", {"bill_ids": ["foreign-bill"]}), ("status", {"payment_key": "foreign-payment"})],
)
def test_foreign_bill_or_payment_is_not_accessible(browser, user, action, payload):
    other = AccountSession.objects.create(mode="live", state="authenticated")
    PaymentAttempt.objects.create(session=other, payment_key="foreign-payment", bill_ids=["foreign-bill"])
    user.account.mode = "live"
    user.account.save()
    response = post(browser, "payment/", {"action": action, **payload})
    assert response.status_code == 400
    assert response.json()["error"]["code"] in {"BILL_NOT_FOUND", "PAYMENT_NOT_FOUND"}


def test_paid_snapshot_hides_link_and_preserves_completion(browser, user):
    op = Operation.objects.create(
        session=user.account,
        action_id="bill_payment",
        idempotency_key="p",
        request_hash="h",
        result={"parameters": {"RedirectLink": "https://bank.example/pay"}},
    )
    attempt = PaymentAttempt.objects.create(
        session=user.account,
        operation=op,
        payment_key="paid-key",
        gateway="OnlinePayment_Sadad_Ghabzino",
        status="Paid",
        bill_ids=["b"],
        bill_statuses=[{"bill_id": "b", "status": "Paid"}],
    )
    PaymentSnapshot.objects.create(
        visitor=user, payment_key=attempt.payment_key, data={"amount": 92000, "fee": 0, "total_amount": 92000}
    )
    card = browser.get("/api/portal/state/").json()["payments"][0]
    assert card["payment_complete"] is True
    assert card["pending"] is False
    assert card["redirect_url"] is None
    assert card["fee"] == 0


def test_missing_fee_stays_null(browser, user):
    PaymentAttempt.objects.create(session=user.account, payment_key="no-fee", status="Unpaid")
    card = browser.get("/api/portal/state/").json()["payments"][0]
    assert card["fee"] is None and card["total_amount"] is None


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "http://bank.example/pay", "https://user:password@bank.example/pay", None]
)
def test_unsafe_links_rejected(url):
    assert services.safe_link(url) is None


def test_https_link_retained():
    assert services.safe_link("https://bank.example/pay") == "https://bank.example/pay"


def test_feedback_and_logout(browser, user):
    assert post(browser, "feedback/", {"rating": 5, "comment": "easy to use"}).status_code == 200
    assert Feedback.objects.get().visitor == user
    assert post(browser, "feedback/", {"rating": 8}).status_code == 400
    post(browser, "logout/", {})
    assert post(browser, "feedback/", {"rating": 5}).status_code == 400


def test_limited_tools_and_budget(browser, user, monkeypatch):
    requests = []

    def handle(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "hello"}}]})

    monkeypatch.setattr(runner, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    r = post(browser, "chat/", {"message": "hello", "client_key": str(uuid.uuid4())})
    assert r.status_code == 200, r.content
    assert AgentDailyUsage.objects.get().messages_used == 1
    names = {x["function"]["name"] for x in requests[0]["tools"]}
    assert names == services.PILOT_TOOLS
    assert requests[0]["max_tokens"] == 1200
    AgentDailyUsage.objects.update(messages_used=10)
    assert (
        post(browser, "chat/", {"message": "eleventh", "client_key": str(uuid.uuid4())}).json()["error"][
            "code"
        ]
        == "agent_daily_limit"
    )
    assert len(requests) == 1


async def downstream(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.parametrize(
    "path", ["/api/tools/", "/api/chat/", "/api/operations/", "/mcp", "/mcp/", "/console/", "/admin/"]
)
@pytest.mark.asyncio
async def test_lan_peer_cannot_access_developer_surfaces(path):
    app = LANBoundary(downstream)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("192.168.1.44", 1234)), base_url="http://test"
    ) as client:
        response = await client.get(path, headers={"X-Forwarded-For": "127.0.0.1"})
    assert response.status_code == 403


@pytest.mark.parametrize(
    "peer,path",
    [
        ("127.0.0.1", "/console/"),
        ("::1", "/mcp"),
        ("192.168.1.44", "/api/portal/state/"),
        ("192.168.1.44", "/"),
        ("192.168.1.44", "/health/"),
    ],
)
@pytest.mark.asyncio
async def test_lan_boundary_allows_portal_and_local_diagnostics(peer, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=LANBoundary(downstream), client=(peer, 1234)),
        base_url="http://test",
    ) as client:
        response = await client.get(path)
    assert response.status_code == 200
