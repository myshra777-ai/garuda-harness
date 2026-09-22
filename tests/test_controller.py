from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from harness.budgets import BudgetExceeded, CallBudget
from harness.controller import ReadOnlyController, main
from harness.errors import ProtocolError, TransportError
from tests.test_session import FAKE_SERVER


def fake_command(tmp_path: Path) -> list[str]:
    script = tmp_path / "fake_mcp.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    return [sys.executable, "-u", str(script)]


def test_controller_executes_happy_path(tmp_path: Path) -> None:
    cmd = fake_command(tmp_path)
    controller = ReadOnlyController("run-1", tmp_path, cmd)

    controller.run(
        [
            ("garuda.briefing", {}),
            ("garuda.entities", {"workspace": "fixture"}),
        ]
    )

    manifest_data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "succeeded"
    assert manifest_data["event_count"] == 2
    assert manifest_data["server_info"]["name"] == "fake-garuda-mcp"

    journal_text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in journal_text.splitlines()]

    event_types = [e["event_type"] for e in events]
    assert event_types[0] == "run.started"
    assert "tool_call.completed" in event_types
    assert event_types[-1] == "run.succeeded"

    # Assert no raw result payload leaked into the journal
    assert all("result" not in event.get("payload", {}) for event in events)


def test_controller_cancels_on_budget_exhaustion(tmp_path: Path) -> None:
    cmd = fake_command(tmp_path)
    budget = CallBudget(max_calls=1)
    controller = ReadOnlyController("run-2", tmp_path, cmd, budget=budget)

    with pytest.raises(BudgetExceeded):
        controller.run(
            [
                ("garuda.briefing", {}),
                ("garuda.entities", {"workspace": "fixture"}),
            ]
        )

    manifest_data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "cancelled"
    assert manifest_data["error"] == "budget exceeded"

    journal_text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in journal_text.splitlines()]
    assert events[-1]["event_type"] == "run.cancelled"
    assert events[-1]["payload"]["reason"] == "budget exceeded"


def test_controller_fails_on_transport_error(tmp_path: Path) -> None:
    cmd = [sys.executable, "-u", "-c", "import sys; sys.exit(1)"]
    controller = ReadOnlyController("run-3", tmp_path, cmd)

    with pytest.raises(TransportError):
        controller.run([("garuda.briefing", {})])

    manifest_data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "failed"
    assert manifest_data["error"] == "session initialization failed"

    journal_text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in journal_text.splitlines()]
    assert events[-1]["event_type"] == "run.failed"


def test_controller_fails_on_protocol_error(tmp_path: Path) -> None:
    bad_server = FAKE_SERVER.replace('"2025-06-18"', '"9999-01-01"', 1)
    script = tmp_path / "bad_mcp.py"
    script.write_text(bad_server, encoding="utf-8")
    cmd = [sys.executable, "-u", str(script)]

    controller = ReadOnlyController("run-4", tmp_path, cmd)

    with pytest.raises(ProtocolError):
        controller.run([("garuda.briefing", {})])

    manifest_data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "failed"
    assert manifest_data["error"] == "session initialization failed: protocol error"

    journal_text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in journal_text.splitlines()]
    assert events[-1]["event_type"] == "run.failed"
    assert events[-1]["payload"]["error"] == "session initialization failed: protocol error"


def test_controller_preserves_cli_contract() -> None:
    assert main([]) == 0
    assert main(["check"]) == 0
    assert main(["run"]) == 2
    assert main(["run", "--read-only"]) == 0
