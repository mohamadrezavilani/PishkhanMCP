from unittest.mock import Mock

import httpx
import pytest
from django.utils import timezone

from apps.agent import runner
from apps.core.models import AccountSession, AgentDailyUsage


@pytest.fixture
def agent_settings(settings):
    settings.AGENT_BASE_URL = "https://api.anthropic.com/v1"
    settings.AGENT_MODEL = "claude-sonnet-4-6"
    settings.AGENT_API_KEY = "test-key"
    settings.AGENT_PROXY_URL = ""
    settings.AGENT_WORKSPACE_ID = ""
    settings.AGENT_DAILY_MESSAGE_LIMIT = 10
    settings.AGENT_MAX_STEPS = 2
    settings.AGENT_TIMEOUT = 10
    return settings


def test_daily_budget_reserves_one_user_turn(db, agent_settings, monkeypatch):
    session = AccountSession.objects.create(mode="demo")
    monkeypatch.setattr(runner, "_list_tools", lambda: [])
    monkeypatch.setattr(
        runner,
        "_make_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
                )
            )
        ),
    )
    result = runner.run_turn(str(session.pk), "سلام")
    assert result["ok"]
    assert result["agent_usage"]["used"] == 1
    assert result["agent_usage"]["remaining"] == 9
    assert AgentDailyUsage.objects.get(usage_date=timezone.localdate()).messages_used == 1


def test_daily_budget_blocks_message_eleven(db, agent_settings, monkeypatch):
    session = AccountSession.objects.create(mode="demo")
    AgentDailyUsage.objects.create(usage_date=timezone.localdate(), messages_used=10)
    client = Mock()
    monkeypatch.setattr(runner, "_make_client", client)
    result = runner.run_turn(str(session.pk), "پیام یازدهم")
    assert result["error"]["code"] == "agent_daily_limit"
    assert result["error"]["details"]["remaining"] == 0
    client.assert_not_called()


def test_socks_proxy_configuration_and_workspace_header(agent_settings):
    agent_settings.AGENT_PROXY_URL = "socks5://user:pass@127.0.0.1:1080"
    agent_settings.AGENT_WORKSPACE_ID = "workspace-test"
    client = runner._make_client()
    try:
        assert client.headers["anthropic-workspace-id"] == "workspace-test"
        assert client._mounts
    finally:
        client.close()
