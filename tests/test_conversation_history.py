"""History conflict regression tests with a deterministic, non-advancing clock."""

from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from apps.agent import runner
from apps.core.models import AccountSession, Conversation


@pytest.fixture
def conversation(db):
    account = AccountSession.objects.create(mode="demo")
    return Conversation.objects.create(session=account)


def test_concurrent_turn_with_identical_timestamp_is_not_overwritten(conversation, settings, monkeypatch):
    """The original timestamp-only lock misses this competing raw ORM update."""
    settings.AGENT_BASE_URL = "https://model.example/v1"
    settings.AGENT_MODEL = "test-model"
    settings.AGENT_MAX_STEPS = 2
    settings.AGENT_DAILY_MESSAGE_LIMIT = 10
    frozen = conversation.updated_at
    monkeypatch.setattr(timezone, "now", lambda: frozen)
    monkeypatch.setattr(runner, "_list_tools", lambda: [])
    winner = [{"role": "assistant", "content": "another completed turn"}]

    def concurrent_response(request):
        Conversation.objects.filter(pk=conversation.pk).update(messages=winner, updated_at=frozen)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "stale turn"}}]}
        )

    monkeypatch.setattr(
        runner, "_make_client", lambda: httpx.Client(transport=httpx.MockTransport(concurrent_response))
    )
    result = runner.run_turn(str(conversation.session_id), "continue", str(conversation.pk))
    assert result["error"]["code"] == "conversation_conflict"
    assert result["ok"] is False
    assert result["stop_reason"] == "conversation_conflict"
    conversation.refresh_from_db()
    assert conversation.messages == winner
    assert conversation.updated_at == frozen


@pytest.mark.parametrize("seconds_delta", [0, -1, 1])
def test_stale_snapshot_rejected_independently_of_clock(conversation, monkeypatch, seconds_delta):
    stale = Conversation.objects.get(pk=conversation.pk)
    changed_time = conversation.updated_at + timedelta(seconds=seconds_delta)
    monkeypatch.setattr(timezone, "now", lambda: changed_time)
    winner = [{"role": "assistant", "content": "first writer"}]
    loser = [{"role": "assistant", "content": "stale writer"}]
    assert runner._save_history(conversation, winner, set()) is True
    assert runner._save_history(stale, loser, set()) is False
    conversation.refresh_from_db()
    assert conversation.messages == winner
    assert conversation.history_version == 1
    assert conversation.updated_at == changed_time
    assert stale.history_version == 0


def test_revision_changes_even_when_history_and_timestamp_do_not(conversation, monkeypatch):
    """A revision check detects writes that an equality-only snapshot cannot."""
    stale = Conversation.objects.get(pk=conversation.pk)
    frozen = conversation.updated_at
    monkeypatch.setattr(timezone, "now", lambda: frozen)
    assert runner._save_history(conversation, [], set()) is True
    assert runner._save_history(stale, [{"role": "assistant", "content": "stale"}], set()) is False
    conversation.refresh_from_db()
    assert conversation.history_version == 1
    assert conversation.messages == []


def test_successful_save_refreshes_local_snapshot_for_next_save(conversation, monkeypatch):
    frozen = conversation.updated_at
    monkeypatch.setattr(timezone, "now", lambda: frozen)
    first = [{"role": "assistant", "content": "first"}]
    second = [*first, {"role": "user", "content": "second"}]
    assert runner._save_history(conversation, first, set()) is True
    assert conversation.messages == first
    assert conversation.history_version == 1
    assert runner._save_history(conversation, second, set()) is True
    conversation.refresh_from_db()
    assert conversation.messages == second
    assert conversation.history_version == 2


def test_deleted_conversation_is_not_recreated_by_history_save(conversation):
    Conversation.objects.filter(pk=conversation.pk).delete()
    assert runner._save_history(conversation, [{"role": "assistant", "content": "late"}], set()) is False
    assert not Conversation.objects.filter(pk=conversation.pk).exists()
