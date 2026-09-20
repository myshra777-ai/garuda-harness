import pytest

from harness.errors import ProtocolError, ReadOnlyViolation
from harness.tools import (
    MUTATING_TOOLS,
    READ_ONLY_TOOLS,
    ToolRegistry,
)


def tool(name: str) -> dict[str, object]:
    return {
        "name": name,
        "description": f"Test tool {name}",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    }


def test_valid_tools_list_parses() -> None:
    registry = ToolRegistry.from_tools_result(
        {
            "tools": [
                tool("garuda.entities"),
                tool("garuda.policy.evaluate"),
            ]
        }
    )

    assert registry.names == {
        "garuda.entities",
        "garuda.policy.evaluate",
    }


def test_tools_list_requires_tools_array() -> None:
    with pytest.raises(ProtocolError):
        ToolRegistry.from_tools_result({})


def test_tools_list_rejects_invalid_entry() -> None:
    with pytest.raises(ProtocolError):
        ToolRegistry.from_tools_result({"tools": ["garuda.entities"]})


def test_tools_list_rejects_duplicate_names() -> None:
    with pytest.raises(ProtocolError):
        ToolRegistry.from_tools_result(
            {
                "tools": [
                    tool("garuda.entities"),
                    tool("garuda.entities"),
                ]
            }
        )


def test_required_read_only_tools_are_detected() -> None:
    registry = ToolRegistry.from_tools_result(
        {
            "tools": [
                tool("garuda.entities"),
            ]
        }
    )

    missing = registry.missing_required_read_only_tools()

    assert "garuda.entities" not in missing
    assert "garuda.briefing" in missing


def test_complete_read_only_surface_passes() -> None:
    tools = [tool(name) for name in READ_ONLY_TOOLS]
    registry = ToolRegistry.from_tools_result({"tools": tools})

    registry.require_complete_read_only_surface()


def test_mutating_tools_are_known_and_blocked() -> None:
    assert MUTATING_TOOLS == {
        "garuda.propose_decision",
        "garuda.handoff",
        "garuda.resume",
    }

    registry = ToolRegistry.from_tools_result(
        {
            "tools": [
                tool("garuda.handoff"),
            ]
        }
    )

    with pytest.raises(ReadOnlyViolation):
        registry.require_read_only("garuda.handoff")


def test_unknown_tools_are_blocked() -> None:
    registry = ToolRegistry.from_tools_result(
        {
            "tools": [
                tool("garuda.entities"),
            ]
        }
    )

    with pytest.raises(ReadOnlyViolation):
        registry.require_read_only("garuda.not_a_real_tool")


def test_advertised_read_only_tool_is_allowed() -> None:
    registry = ToolRegistry.from_tools_result(
        {
            "tools": [
                tool("garuda.entities"),
            ]
        }
    )

    definition = registry.require_read_only("garuda.entities")

    assert definition.name == "garuda.entities"
