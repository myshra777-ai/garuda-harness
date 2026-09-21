"""Atomic JSON run manifests for bounded harness executions."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

MANIFEST_SCHEMA_VERSION = 1
MAX_ERROR_LENGTH = 2_000
VALID_STATUSES = frozenset({"running", "succeeded", "failed", "cancelled"})
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


class RunManifest:
    def __init__(self, path: str | Path, data: dict[str, JSONValue]) -> None:
        self.path = Path(path)
        self._data = data

    @classmethod
    def start(
        cls,
        path: str | Path,
        run_id: str,
        read_only: bool,
    ) -> RunManifest:
        if not run_id:
            raise ValueError("run_id must not be empty")

        manifest = cls(
            path,
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "run_id": run_id,
                "status": "running",
                "read_only": read_only,
                "started_at": _utc_now(),
                "finished_at": None,
                "protocol_version": None,
                "server_info": {},
                "journal_path": None,
                "event_count": 0,
                "error": None,
                "error_truncated": False,
            },
        )
        manifest._write()
        return manifest

    def update(
        self,
        *,
        protocol_version: str | None = None,
        server_info: Mapping[str, JSONValue] | None = None,
        journal_path: str | None = None,
        event_count: int | None = None,
    ) -> None:
        if protocol_version is not None:
            if not protocol_version:
                raise ValueError("protocol_version must not be empty")
            self._data["protocol_version"] = protocol_version

        if server_info is not None:
            self._data["server_info"] = _copy_json_object(server_info)

        if journal_path is not None:
            if not journal_path:
                raise ValueError("journal_path must not be empty")
            self._data["journal_path"] = journal_path

        if event_count is not None:
            if event_count < 0:
                raise ValueError("event_count must not be negative")
            self._data["event_count"] = event_count

        self._write()

    def finish(self, status: str, error: str | None = None) -> None:
        if status not in VALID_STATUSES or status == "running":
            raise ValueError(
                "final status must be succeeded, failed, or cancelled"
            )

        current_status = self._data["status"]
        if current_status != "running":
            raise ValueError(f"run is already terminal: {current_status}")

        if status in {"failed", "cancelled"} and not error:
            raise ValueError(f"{status} manifests require a reason")

        if status == "succeeded" and error is not None:
            raise ValueError("succeeded manifests cannot include an error")

        bounded_error, truncated = _bound_error(error)
        self._data["status"] = status
        self._data["finished_at"] = _utc_now()
        self._data["error"] = bounded_error
        self._data["error_truncated"] = truncated
        self._write()

    def snapshot(self) -> dict[str, JSONValue]:
        return _copy_json_object(self._data)

    def _write(self) -> None:
        encoded = json.dumps(
            self._data,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=self.path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _bound_error(error: str | None) -> tuple[str | None, bool]:
    if error is None:
        return None, False
    if len(error) <= MAX_ERROR_LENGTH:
        return error, False
    return error[:MAX_ERROR_LENGTH], True


def _copy_json_object(value: Mapping[str, JSONValue]) -> dict[str, JSONValue]:
    copied = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    if not isinstance(copied, dict):
        raise TypeError("value must be a JSON object")
    return copied
