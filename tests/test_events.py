# tests/test_events.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.events import EventJournal


def test_append_creates_parent_directory_and_jsonl(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path / "nested" / "events.jsonl")

    event = journal.append(
        "run-1",
        "run.started",
        {"mode": "read-only"},
    )

    assert event["schema_version"] == 1
    assert event["run_id"] == "run-1"
    assert event["event_type"] == "run.started"
    assert isinstance(event["occurred_at"], str)
    assert event["occurred_at"].endswith("Z")

    lines = journal.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == event


def test_events_are_appended_in_order(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path / "events.jsonl")

    journal.append("run-1", "run.started", {})
    journal.append("run-1", "tool.completed", {"tool_name": "garuda.entities"})

    records = [
        json.loads(line)
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]

    assert [record["event_type"] for record in records] == [
        "run.started",
        "tool.completed",
    ]


def test_empty_identifiers_are_rejected(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path / "events.jsonl")

    with pytest.raises(ValueError, match="run_id"):
        journal.append("", "run.started", {})

    with pytest.raises(ValueError, match="event_type"):
        journal.append("run-1", "", {})


def test_non_json_payload_is_rejected(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path / "events.jsonl")

    with pytest.raises((TypeError, ValueError)):
        journal.append("run-1", "run.started", {"value": object()})  # type: ignore[dict-item]


def test_payload_is_copied(tmp_path: Path) -> None:
    journal = EventJournal(tmp_path / "events.jsonl")
    payload = {"nested": {"value": 1}}

    event = journal.append("run-1", "run.started", payload)
    payload["nested"]["value"] = 2

    assert event["payload"] == {"nested": {"value": 1}}
