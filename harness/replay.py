"""Offline replay capabilities for bounded harness executions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .events import EVENT_SCHEMA_VERSION

_REQUIRED_EVENT_FIELDS = {
    "schema_version",
    "run_id",
    "event_type",
    "occurred_at",
    "payload",
}


def replay_journal(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield validated events from an append-only JSONL journal."""
    journal_path = Path(path)
    if not journal_path.is_file():
        raise FileNotFoundError(f"journal file not found: {journal_path}")

    run_id: str | None = None
    with journal_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"malformed JSON event at line {line_number}: {exc}"
                ) from exc

            _validate_event(event, line_number)
            event_run_id = event["run_id"]
            if run_id is None:
                run_id = event_run_id
            elif event_run_id != run_id:
                raise ValueError(
                    f"event at line {line_number} belongs to run "
                    f"{event_run_id!r}, expected {run_id!r}"
                )

            yield event


def _validate_event(event: object, line_number: int) -> None:
    if not isinstance(event, dict):
        raise TypeError(f"event at line {line_number} must be a JSON object")

    missing = sorted(_REQUIRED_EVENT_FIELDS - event.keys())
    if missing:
        raise ValueError(
            f"event at line {line_number} is missing fields: "
            + ", ".join(missing)
        )

    if event["schema_version"] != EVENT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported event schema at line {line_number}: "
            f"{event['schema_version']!r}"
        )
    if not isinstance(event["run_id"], str) or not event["run_id"]:
        raise ValueError(f"event at line {line_number} has invalid run_id")
    if not isinstance(event["event_type"], str) or not event["event_type"]:
        raise ValueError(f"event at line {line_number} has invalid event_type")
    if not isinstance(event["occurred_at"], str) or not event["occurred_at"]:
        raise ValueError(f"event at line {line_number} has invalid occurred_at")
    if not isinstance(event["payload"], dict):
        raise TypeError(f"event at line {line_number} has invalid payload")
