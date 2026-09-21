from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness.manifest import (
    MAX_ERROR_LENGTH,
    TERMINAL_STATUSES,
    VALID_STATUSES,
    RunManifest,
)


def test_start_writes_running_manifest(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "run.json"

    manifest = RunManifest.start(path, run_id="run-1", read_only=True)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data == manifest.snapshot()
    assert data["schema_version"] == 1
    assert data["run_id"] == "run-1"
    assert data["status"] == "running"
    assert data["read_only"] is True
    assert data["finished_at"] is None
    assert data["started_at"].endswith("Z")


def test_update_persists_explicit_metadata(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)
    server_info = {"name": "fake", "version": "0.1.0"}

    manifest.update(
        protocol_version="2025-06-18",
        server_info=server_info,
        journal_path="events.jsonl",
        event_count=3,
    )
    server_info["name"] = "changed"

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["protocol_version"] == "2025-06-18"
    assert data["server_info"] == {"name": "fake", "version": "0.1.0"}
    assert data["journal_path"] == "events.jsonl"
    assert data["event_count"] == 3


def test_finish_succeeded(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)

    manifest.finish("succeeded")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["status"] == "succeeded"
    assert data["finished_at"].endswith("Z")
    assert data["error"] is None
    assert data["error_truncated"] is False


def test_finish_failed_bounds_error(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)
    error = "x" * (MAX_ERROR_LENGTH + 100)

    manifest.finish("failed", error)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["status"] == "failed"
    assert data["error"] == error[:MAX_ERROR_LENGTH]
    assert data["error_truncated"] is True


def test_finish_cancelled_requires_reason(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)

    with pytest.raises(ValueError, match="cancelled manifests require"):
        manifest.finish("cancelled")

    manifest.finish("cancelled", "cancelled by operator")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["status"] == "cancelled"
    assert data["finished_at"].endswith("Z")
    assert data["error"] == "cancelled by operator"
    assert data["error_truncated"] is False


def test_terminal_manifest_cannot_be_finished_again(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)

    manifest.finish("cancelled", "budget exhausted")

    with pytest.raises(ValueError, match="already terminal"):
        manifest.finish("succeeded")


def test_manifest_status_sets_are_explicit() -> None:
    assert VALID_STATUSES == {
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }
    assert TERMINAL_STATUSES == {
        "succeeded",
        "failed",
        "cancelled",
    }


def test_invalid_inputs_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run_id"):
        RunManifest.start(tmp_path / "run.json", run_id="", read_only=True)

    manifest = RunManifest.start(tmp_path / "run.json", run_id="run-1", read_only=True)

    with pytest.raises(ValueError, match="negative"):
        manifest.update(event_count=-1)
    with pytest.raises(ValueError, match="succeeded, failed, or cancelled"):
        manifest.finish("running")
    with pytest.raises(ValueError, match="require a reason"):
        manifest.finish("failed")
    with pytest.raises(ValueError, match="cannot include"):
        manifest.finish("succeeded", "unexpected")


def test_non_json_server_info_is_rejected_without_replacing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)
    before = path.read_text(encoding="utf-8")

    with pytest.raises((TypeError, ValueError)):
        manifest.update(server_info={"value": object()})  # type: ignore[dict-item]

    assert path.read_text(encoding="utf-8") == before


def test_failed_persistence_preserves_state_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "run.json"
    manifest = RunManifest.start(path, run_id="run-1", read_only=True)

    original_data = json.loads(path.read_text(encoding="utf-8"))

    def mock_replace(src: str | Path, dst: str | Path) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(OSError, match="simulated disk failure"):
        manifest.update(event_count=5)

    assert manifest.snapshot()["event_count"] == 0
    assert json.loads(path.read_text(encoding="utf-8")) == original_data

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == "run.json"

    monkeypatch.undo()
    manifest.update(event_count=10)

    assert manifest.snapshot()["event_count"] == 10
    assert json.loads(path.read_text(encoding="utf-8"))["event_count"] == 10
