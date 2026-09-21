from __future__ import annotations

import pytest

from harness.redaction import redact_tool_arguments


def test_safe_fields_are_retained_and_unknown_fields_are_omitted() -> None:
    arguments = {
        "workspace": "fixture",
        "package": "payments",
        "limit": 10,
        "token": "secret",
        "prompt": "private context",
    }

    result = redact_tool_arguments("garuda.entities", arguments)

    assert result == {
        "workspace": "fixture",
        "package": "payments",
        "limit": 10,
    }
    assert arguments["token"] == "secret"


def test_free_form_query_is_never_recorded() -> None:
    result = redact_tool_arguments(
        "garuda.query",
        {"query": "customer payment architecture", "workspace": "fixture"},
    )

    assert result == {}


def test_unknown_tool_fails_closed() -> None:
    result = redact_tool_arguments(
        "garuda.unknown",
        {"workspace": "fixture", "safe": "value"},
    )

    assert result == {}


def test_none_arguments_return_empty_mapping() -> None:
    assert redact_tool_arguments("garuda.entities", None) == {}


def test_nested_json_values_are_copied() -> None:
    nested = {"workspace": "fixture", "limit": [1, {"value": 2}]}

    result = redact_tool_arguments("garuda.entities", nested)
    nested["limit"].append(3)

    assert result == {"workspace": "fixture", "limit": [1, {"value": 2}]}


def test_non_json_values_are_rejected() -> None:
    with pytest.raises(TypeError, match="non-JSON value"):
        redact_tool_arguments("garuda.entities", {"limit": object()})