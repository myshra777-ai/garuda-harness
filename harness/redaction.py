"""Fail-closed redaction for persisted MCP tool arguments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

SAFE_ARGUMENTS: dict[str, frozenset[str]] = {
    "garuda.briefing": frozenset({"workspace"}),
    "garuda.entities": frozenset({"workspace", "package", "kind", "limit"}),
    "garuda.find_entity": frozenset(
        {"workspace", "name_pattern", "kind", "package", "limit"}
    ),
    "garuda.inspect": frozenset({"workspace", "entity_id"}),
    "garuda.neighbors": frozenset({"workspace", "entity_id", "limit"}),
    "garuda.subclasses": frozenset(
        {"workspace", "entity_id", "name", "language", "limit"}
    ),
    "garuda.implementers": frozenset({"workspace", "entity_id", "name", "limit"}),
    "garuda.blast_radius": frozenset(
        {"workspace", "entity_id", "depth", "min_confidence"}
    ),
    "garuda.query_claims": frozenset({"workspace", "subject"}),
    "garuda.query": frozenset(),
    "garuda.policy.list": frozenset({"tenant_id"}),
    "garuda.policy.evaluate": frozenset({"workspace"}),
    "garuda.verify_policy_evaluation": frozenset({"evaluation_id", "tenant_id"}),
    "garuda.governance.status": frozenset({"workspace"}),
    "garuda.check_drift": frozenset({"workspace"}),
    "garuda.get_lineage": frozenset({"decision_id", "tenant_id"}),
    "garuda.get_impact": frozenset({"decision_id", "tenant_id"}),
    "garuda.detect_contradictions": frozenset({"tenant_id"}),
}


def redact_tool_arguments(
    tool_name: str,
    arguments: Mapping[str, object] | None,
) -> dict[str, JSONValue]:
    """Return a safe, JSON-compatible allowlisted copy of tool arguments."""
    if arguments is None:
        return {}

    allowed = SAFE_ARGUMENTS.get(tool_name, frozenset())
    redacted: dict[str, JSONValue] = {}
    for key in allowed:
        if key in arguments:
            redacted[key] = _copy_json_value(arguments[key], f"arguments[{key!r}]")
    return redacted


def _copy_json_value(value: object, path: str) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_copy_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, dict):
        copied: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string object key")
            copied[key] = _copy_json_value(item, f"{path}.{key}")
        return copied
    raise TypeError(f"{path} contains a non-JSON value: {type(value).__name__}")