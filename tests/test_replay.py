from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.events import EventJournal
from harness.replay import replay_journal


def test_replay_journal_yields_events_in_order(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    journal = EventJournal(path)

    # Write some events
    journal.append("run-1", "run.started", {"mode": "read-only"})
    journal.append("run-1", "tool.called", {"tool": "garuda.entities"})
    journal.append("run-1", "run.succeeded", {})

    # Replay them
    events = list(replay_journal(path))

    assert len(events) == 3
    assert events[0]["event_type"] == "run.started"
    assert events[1]["event_type"] == "tool.called"
    assert events[2]["event_type"] == "run.succeeded"

    # Verify payloads are intact
    assert events[0]["payload"] == {"mode": "read-only"}
    assert events[1]["payload"] == {"tool": "garuda.entities"}


def test_replay_journal_fails_if_file_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "does_not_exist.jsonl"

    with pytest.raises(FileNotFoundError, match="journal file not found"):
        # The generator must be consumed to trigger the exception
        list(replay_journal(missing_path))


def test_replay_journal_fails_on_corrupted_json(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.jsonl"

    # Manually write a file with a bad line
    valid_event = json.dumps(
        {
            "schema_version": 1,
            "run_id": "run-1",
            "event_type": "valid",
            "occurred_at": "2026-09-21T00:00:00Z",
            "payload": {},
        }
    )
    path.write_text(f"{valid_event}\n{{bad_json: true\n", encoding="utf-8")

    replayer = replay_journal(path)

    # First event should yield fine
    first = next(replayer)
    assert first["event_type"] == "valid"

    # Second event should explode with line number 2
    with pytest.raises(ValueError, match="malformed JSON event at line 2"):
        next(replayer)



def test_replay_rejects_mixed_run_ids(tmp_path: Path) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "run-1",
                "event_type": "run.started",
                "occurred_at": "2026-09-21T00:00:00Z",
                "payload": {},
            }
        )
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "run_id": "run-2",
                "event_type": "run.started",
                "occurred_at": "2026-09-21T00:00:01Z",
                "payload": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="belongs to run"):
        list(replay_journal(path))


def test_replay_rejects_missing_event_fields(tmp_path: Path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps({"run_id": "run-1"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing fields"):
        list(replay_journal(path))


def test_replay_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "run_id": "run-1",
                "event_type": "run.started",
                "occurred_at": "2026-09-21T00:00:00Z",
                "payload": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported event schema"):
        list(replay_journal(path))
