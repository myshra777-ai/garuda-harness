import json
import sys
from pathlib import Path
from typing import Any

import pytest

from harness.budgets import BudgetExceeded, CallBudget
from harness.errors import ProtocolError, ReadOnlyViolation
from harness.events import EventJournal
from harness.session import open_read_only_session, result_digest
from harness.tools import READ_ONLY_TOOLS

FAKE_SERVER = r"""
import json
import sys

READ_ONLY = [
    "garuda.briefing",
    "garuda.entities",
    "garuda.find_entity",
    "garuda.inspect",
    "garuda.neighbors",
    "garuda.subclasses",
    "garuda.implementers",
    "garuda.blast_radius",
    "garuda.query_claims",
    "garuda.query",
    "garuda.policy.list",
    "garuda.policy.evaluate",
    "garuda.verify_policy_evaluation",
    "garuda.governance.status",
    "garuda.check_drift",
    "garuda.get_lineage",
    "garuda.get_impact",
    "garuda.detect_contradictions",
]

for line in sys.stdin:
    request = json.loads(line)

    if "id" not in request:
        continue

    method = request["method"]

    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "serverInfo": {
                "name": "fake-garuda-mcp",
                "version": "0.1.0",
            },
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": name,
                    "description": f"Fake {name}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                }
                for name in READ_ONLY
            ]
        }
    elif method == "tools/call":
        result = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"status": "ok"}),
                }
            ]
        }
    else:
        result = {}

    sys.stdout.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": result,
            }
        )
        + "\n"
    )
    sys.stdout.flush()
"""


def fake_command() -> list[str]:
    return [sys.executable, "-u", "-c", FAKE_SERVER]


def test_open_read_only_session() -> None:
    session = open_read_only_session(fake_command())

    try:
        assert session.protocol_version == "2025-06-18"
        assert session.server_info["name"] == "fake-garuda-mcp"
        assert session.tools.names == READ_ONLY_TOOLS
    finally:
        assert session.close() == 0


def test_read_only_tool_call_is_allowed() -> None:
    session = open_read_only_session(fake_command())

    try:
        call = session.call_read_only(
            "garuda.entities",
            {"workspace": "fixture"},
        )
        assert call.is_error is False
        assert call.result["content"][0]["type"] == "text"
    finally:
        assert session.close() == 0


def test_mutating_tool_call_is_rejected_before_transport() -> None:
    session = open_read_only_session(fake_command())

    try:
        with pytest.raises(ReadOnlyViolation):
            session.call_read_only("garuda.handoff", {})
    finally:
        assert session.close() == 0


def test_protocol_version_mismatch_is_rejected() -> None:
    bad_server = FAKE_SERVER.replace(
        '"2025-06-18"',
        '"9999-01-01"',
        1,
    )
    session_command = [sys.executable, "-u", "-c", bad_server]

    with pytest.raises(ProtocolError, match="unsupported MCP protocol version"):
        open_read_only_session(session_command)


def test_missing_required_tool_is_rejected() -> None:
    incomplete_server = FAKE_SERVER.replace(
        '"garuda.briefing",\n',
        "",
        1,
    )
    session_command = [sys.executable, "-u", "-c", incomplete_server]

    with pytest.raises(ProtocolError, match="missing required read-only tools"):
        open_read_only_session(session_command)


def test_read_only_call_result_exposes_result() -> None:
    session = open_read_only_session(fake_command())

    try:
        call = session.call_read_only(
            "garuda.entities",
            {"workspace": "fixture"},
        )

        assert call.tool_name == "garuda.entities"
        assert call.is_error is False
        assert call.result["content"][0]["type"] == "text"
    finally:
        assert session.close() == 0


def test_tool_error_is_preserved() -> None:
    error_server = FAKE_SERVER.replace(
        'result = {\n            "content": [\n                {\n                    "type": "text",\n                    "text": json.dumps({"status": "ok"}),\n                }\n            ]\n        }',
        'result = {"error": "fixture failure"}',
        1,
    )
    session = open_read_only_session(
        [sys.executable, "-u", "-c", error_server]
    )

    try:
        call = session.call_read_only("garuda.entities", {})
        assert call.is_error is False
        assert call.result["error"] == "fixture failure"
    finally:
        assert session.close() == 0


def test_session_budget_permits_calls_within_limit() -> None:
    budget = CallBudget(max_calls=2)
    session = open_read_only_session(fake_command(), budget=budget)

    try:
        call = session.call_read_only("garuda.entities", {"workspace": "fixture"})
        assert call.is_error is False
        assert budget.call_count == 1
    finally:
        assert session.close() == 0


def test_session_rejects_second_call_when_budget_is_one() -> None:
    budget = CallBudget(max_calls=1)
    session = open_read_only_session(fake_command(), budget=budget)

    try:
        session.call_read_only("garuda.entities", {"workspace": "one"})
        assert budget.call_count == 1

        with pytest.raises(BudgetExceeded, match="maximum call budget"):
            session.call_read_only("garuda.entities", {"workspace": "two"})
    finally:
        assert session.close() == 0


def test_session_rejects_repeated_calls() -> None:
    budget = CallBudget(max_repeated_calls=1)
    session = open_read_only_session(fake_command(), budget=budget)

    try:
        session.call_read_only("garuda.entities", {"workspace": "fixture"})

        with pytest.raises(BudgetExceeded, match="repeated-call budget"):
            session.call_read_only("garuda.entities", {"workspace": "fixture"})
    finally:
        assert session.close() == 0


def test_session_rejects_oversized_result() -> None:
    budget = CallBudget(max_result_bytes=10)
    session = open_read_only_session(fake_command(), budget=budget)

    try:
        with pytest.raises(BudgetExceeded, match="result-size budget"):
            session.call_read_only("garuda.entities", {"workspace": "fixture"})
    finally:
        assert session.close() == 0


def test_session_without_budget_preserves_behavior() -> None:
    session = open_read_only_session(fake_command())

    try:
        call1 = session.call_read_only("garuda.entities", {"workspace": "fixture"})
        call2 = session.call_read_only("garuda.entities", {"workspace": "fixture"})

        assert call1.is_error is False
        assert call2.is_error is False
    finally:
        assert session.close() == 0


def test_budget_is_attached_to_session() -> None:
    budget = CallBudget()
    session = open_read_only_session(fake_command(), budget=budget)

    try:
        assert session.budget is budget
    finally:
        assert session.close() == 0


def test_result_digest_is_canonical() -> None:
    result_1 = {"b": 2, "a": 1}
    result_2 = {"a": 1, "b": 2}
    assert result_digest(result_1) == result_digest(result_2)


def test_session_journals_redacted_call_and_digest_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_path = tmp_path / "events.jsonl"
    journal = EventJournal(journal_path)

    def mock_redact(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"allowlisted": True, "original_keys": list(args.keys())}

    monkeypatch.setattr("harness.session.redact_tool_arguments", mock_redact)

    session = open_read_only_session(
        fake_command(),
        journal=journal,
        run_id="run-test",
    )

    try:
        session.call_read_only("garuda.entities", {"workspace": "fixture"})

        events = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
        ]

        assert len(events) == 2

        started = events[0]
        assert started["event_type"] == "tool_call.started"
        assert started["payload"]["tool_name"] == "garuda.entities"
        assert started["payload"]["arguments"] == {
            "allowlisted": True,
            "original_keys": ["workspace"],
        }

        completed = events[1]
        assert completed["event_type"] == "tool_call.completed"
        assert completed["payload"]["tool_name"] == "garuda.entities"
        assert completed["payload"]["status"] == "ok"
        assert "result_digest" in completed["payload"]
        assert completed["payload"]["result_bytes"] > 0
        assert "result" not in completed["payload"]

    finally:
        assert session.close() == 0


def test_session_journals_tool_failure(tmp_path: Path) -> None:
    journal_path = tmp_path / "events.jsonl"
    journal = EventJournal(journal_path)

    error_server = FAKE_SERVER.replace(
        'result = {\n            "content": [\n                {\n                    "type": "text",\n                    "text": json.dumps({"status": "ok"}),\n                }\n            ]\n        }',
        'result = {"error": "fixture failure"}',
        1,
    )

    session = open_read_only_session(
        [sys.executable, "-u", "-c", error_server],
        journal=journal,
        run_id="run-fail",
    )

    try:
        session.call_read_only("garuda.entities", {})

        events = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
        ]

        assert len(events) == 2
        assert events[0]["event_type"] == "tool_call.started"
        assert events[1]["event_type"] == "tool_call.failed"
        assert events[1]["payload"]["tool_name"] == "garuda.entities"
        assert events[1]["payload"]["error"] == "fixture failure"

    finally:
        assert session.close() == 0


def test_budget_rejection_emits_no_transport_call_or_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal_path = tmp_path / "events.jsonl"
    journal = EventJournal(journal_path)
    budget = CallBudget(max_calls=1)

    def mock_redact(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {}

    monkeypatch.setattr("harness.session.redact_tool_arguments", mock_redact)

    session = open_read_only_session(
        fake_command(),
        budget=budget,
        journal=journal,
        run_id="run-budget",
    )

    try:
        session.call_read_only("garuda.entities", {})

        with pytest.raises(BudgetExceeded):
            session.call_read_only("garuda.entities", {"workspace": "two"})

        events = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
        ]

        assert len(events) == 2
        assert events[0]["event_type"] == "tool_call.started"
        assert events[1]["event_type"] == "tool_call.completed"

    finally:
        assert session.close() == 0


def test_existing_sessions_without_journal_still_work() -> None:
    session = open_read_only_session(fake_command())

    try:
        call = session.call_read_only("garuda.entities", {"workspace": "fixture"})
        assert call.is_error is False
    finally:
        assert session.close() == 0