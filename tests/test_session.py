import sys

import pytest

from harness.budgets import BudgetExceeded, CallBudget
from harness.errors import ProtocolError, ReadOnlyViolation
from harness.session import open_read_only_session
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