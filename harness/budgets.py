"""Bounded call accounting for read-only harness runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TypeAlias

from .errors import HarnessError

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class BudgetExceeded(HarnessError):
    """A configured harness budget was exceeded."""


class CallBudget:
    def __init__(
        self,
        max_calls: int = 100,
        max_repeated_calls: int = 3,
        max_result_bytes: int = 1_000_000,
    ) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if max_repeated_calls <= 0:
            raise ValueError("max_repeated_calls must be positive")
        if max_result_bytes <= 0:
            raise ValueError("max_result_bytes must be positive")

        self.max_calls = max_calls
        self.max_repeated_calls = max_repeated_calls
        self.max_result_bytes = max_result_bytes
        self.call_count = 0
        self._repeated_calls: dict[str, int] = {}

    def before_call(
        self,
        tool_name: str,
        arguments: Mapping[str, JSONValue],
    ) -> None:
        if self.call_count >= self.max_calls:
            raise BudgetExceeded(
                f"maximum call budget exceeded: {self.max_calls}"
            )

        identity = _call_identity(tool_name, arguments)
        repeated_count = self._repeated_calls.get(identity, 0)
        if repeated_count >= self.max_repeated_calls:
            raise BudgetExceeded(
                "maximum repeated-call budget exceeded for "
                f"{tool_name}: {self.max_repeated_calls}"
            )

        self.call_count += 1
        self._repeated_calls[identity] = repeated_count + 1

    def record_result(self, result: JSONValue) -> None:
        encoded = json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > self.max_result_bytes:
            raise BudgetExceeded(
                "maximum result-size budget exceeded: "
                f"{len(encoded)} > {self.max_result_bytes} bytes"
            )


def _call_identity(
    tool_name: str,
    arguments: Mapping[str, JSONValue],
) -> str:
    encoded = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"{tool_name}\x00{encoded}"