"""Dynamic MCP tool registry and H1 read-only policy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .errors import ProtocolError, ReadOnlyViolation

READ_ONLY_TOOLS = frozenset(
    {
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
    }
)

MUTATING_TOOLS = frozenset(
    {
        "garuda.propose_decision",
        "garuda.handoff",
        "garuda.resume",
    }
)

REQUIRED_READ_ONLY_TOOLS = frozenset(
    {
        "garuda.briefing",
        "garuda.entities",
        "garuda.find_entity",
        "garuda.policy.evaluate",
        "garuda.blast_radius",
    }
)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolDefinition]) -> None:
        definitions = tuple(tools)
        names = [tool.name for tool in definitions]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ProtocolError(
                "tools/list contains duplicate tool names: "
                + ", ".join(duplicates)
            )

        self._tools = {tool.name: tool for tool in definitions}

    @classmethod
    def from_tools_result(cls, result: dict[str, Any]) -> ToolRegistry:
        raw_tools = result.get("tools")
        if not isinstance(raw_tools, list):
            raise ProtocolError("tools/list result must contain a tools array")

        definitions: list[ToolDefinition] = []
        for index, raw_tool in enumerate(raw_tools):
            if not isinstance(raw_tool, dict):
                raise ProtocolError(f"tools/list entry {index} must be an object")

            name = raw_tool.get("name")
            description = raw_tool.get("description", "")
            input_schema = raw_tool.get("inputSchema", {})

            if not isinstance(name, str) or not name:
                raise ProtocolError(f"tools/list entry {index} has invalid name")
            if not isinstance(description, str):
                raise ProtocolError(f"tool {name} has invalid description")
            if not isinstance(input_schema, dict):
                raise ProtocolError(f"tool {name} has invalid inputSchema")

            definitions.append(
                ToolDefinition(
                    name=name,
                    description=description,
                    input_schema=input_schema,
                )
            )

        return cls(definitions)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    @property
    def tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    def missing_required_read_only_tools(self) -> frozenset[str]:
        return frozenset(REQUIRED_READ_ONLY_TOOLS - self.names)

    def require_read_only(self, name: str) -> ToolDefinition:
        if name in MUTATING_TOOLS:
            raise ReadOnlyViolation(f"mutating tool is disabled in H1 read-only mode: {name}")
        if name not in READ_ONLY_TOOLS:
            raise ReadOnlyViolation(f"tool is not approved for H1 read-only mode: {name}")
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ReadOnlyViolation(f"tool was not advertised by tools/list: {name}") from exc

    def require_complete_read_only_surface(self) -> None:
        missing = self.missing_required_read_only_tools()
        if missing:
            raise ProtocolError(
                "MCP server is missing required read-only tools: "
                + ", ".join(sorted(missing))
            )
