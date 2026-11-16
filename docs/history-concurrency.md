# Conversation history conflict fix

## Reproduction

The history writer used `updated_at` as its optimistic-lock token. Two writes
can have the same timestamp. A competing turn then changes the history without
changing that token, and the stale turn overwrites it. The caller receives a
success rather than `conversation_conflict`, so the reported test raises
`KeyError: 'error'`.

The regression test fixes `timezone.now()` to the original row's timestamp.
On the previous implementation it reproduces that exact KeyError, without
threads, sleeping, a live model, or any platform-specific clock assumptions.
This demonstrates the code defect; it is not a measurement of the user's clock.

## Fix

`Conversation.history_version` is an integer revision, starting at zero. The
writer performs one conditional database UPDATE with the loaded revision and
history snapshot in the WHERE clause. That same UPDATE increments the revision
with `F("history_version") + 1`. A stale writer updates no rows and returns the
existing `conversation_conflict` response. `updated_at` remains display/audit
metadata, not a lock token.

The snapshot predicate also detects a changed history written by a legacy or
admin path that does not increment the revision. Application history writers
must use `_save_history`; arbitrary database writes are not serialized by this
helper. Successful saves refresh the caller's in-memory snapshot. Failed saves
leave the winner's data untouched.

This prevents lost history updates. It does not serialize whole model turns,
refund model requests, undo already executed tools, or automatically replay
financial operations after a conflict.

## Upgrade (PowerShell)

Stop Uvicorn before applying the migration:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m pytest -q tests/test_agent.py::test_concurrent_history_update_is_not_silently_overwritten tests/test_conversation_history.py
.\.venv\Scripts\python.exe -m pytest -q
```

Migration `core.0004_conversation_history_version` adds a field; do not delete
the database or migration history. Existing sessions/conversations remain.
No model/proxy credentials or `.env` changes are required for this fix.

## Verification

Local Python 3.13 / SQLite: 127 tests passed; Ruff lint/format and Django checks
passed. A separate upgrade check migrated a pre-0004 conversation, preserving
its ID, messages and timestamps with history_version initialized to zero.
The CI matrix now includes Ubuntu and Windows with Python 3.12 and 3.13; read
the specific commit's CI result for the observed outcomes, not this matrix alone.
The original test is retained unchanged. Seven added test cases cover identical,
backward and forward timestamps, same-content saves, stale writers, consecutive
valid saves, a raw ORM competing update and deletion during a turn. Tests use
mock model responses and do not spend Claude credit.
