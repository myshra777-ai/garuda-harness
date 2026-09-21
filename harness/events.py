"""Append-only JSONL event journal for bounded harness runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from .redaction import JSONValue

EVENT_SCHEMA_VERSION = 1


class EventJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, JSONValue],
    ) -> dict[str, JSONValue]:
        if not run_id:
            raise ValueError("run_id must not be empty")
        if not event_type:
            raise ValueError("event_type must not be empty")

        event: dict[str, JSONValue] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "run_id": run_id,
            "event_type": event_type,
            "occurred_at": _utc_now(),
            "payload": _copy_payload(payload),
        }

        encoded = json.dumps(
            event,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.write("\n")
            handle.flush()

        return event


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _copy_payload(payload: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    copied = json.loads(
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    )
    if not isinstance(copied, dict):
        raise TypeError("event payload must be an object")
    return copied
