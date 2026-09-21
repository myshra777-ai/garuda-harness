"""Read-only MCP session bootstrap for H1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from harness.budgets import CallBudget
from harness.events import EventJournal
from harness.redaction import redact_tool_arguments

from .errors import ProtocolError
from .protocol import MCPResponse, MCPStdioClient
from .tools import ToolRegistry

EXPECTED_PROTOCOL_VERSION = "2025-06-18"


def result_digest(result: dict[str, Any]) -> str:
    """Returns a deterministic SHA-256 digest of canonical JSON."""
    encoded = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ToolCallResult:
    tool_name: str
    response: MCPResponse

    @property
    def is_error(self) -> bool:
        return self.response.error is not None

    @property
    def result(self) -> dict[str, Any]:
        if self.response.error is not None:
            raise ProtocolError(
                f"tool {self.tool_name} returned an MCP error: "
                f"{self.response.error}"
            )
        if self.response.result is None:
            raise ProtocolError(f"tool {self.tool_name} returned no result")
        return self.response.result


@dataclass
class ReadOnlySession:
    client: MCPStdioClient
    tools: ToolRegistry
    protocol_version: str
    server_info: dict[str, Any]
    budget: CallBudget | None = None
    journal: EventJournal | None = None
    run_id: str | None = None

    def close(self) -> int:
        return self.client.close()

    def call_read_only(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        self.tools.require_read_only(tool_name)
        safe_args = arguments or {}

        if self.budget is not None:
            self.budget.before_call(tool_name, safe_args)

        if self.journal is not None and self.run_id is not None:
            redacted_args = redact_tool_arguments(tool_name, safe_args)
            self.journal.append(
                self.run_id,
                "tool_call.started",
                {
                    "tool_name": tool_name,
                    "arguments": redacted_args,
                },
            )

        response = self.client.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": safe_args,
            },
        )

        # Handle both JSON-RPC protocol errors and tool-level execution errors
        error_detail = None
        res = response.result if response.result is not None else {}

        if response.error is not None:
            error_detail = response.error
        elif "error" in res:
            error_detail = res["error"]
        elif res.get("isError") is True:
            error_detail = res

        if error_detail is not None:
            if self.journal is not None and self.run_id is not None:
                self.journal.append(
                    self.run_id,
                    "tool_call.failed",
                    {
                        "tool_name": tool_name,
                        "error": error_detail,
                    },
                )
        else:
            encoded = json.dumps(
                res,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            result_bytes = len(encoded)

            if self.budget is not None:
                self.budget.record_result(res)

            if self.journal is not None and self.run_id is not None:
                self.journal.append(
                    self.run_id,
                    "tool_call.completed",
                    {
                        "tool_name": tool_name,
                        "status": "ok",
                        "result_bytes": result_bytes,
                        "result_digest": result_digest(res),
                    },
                )

        return ToolCallResult(tool_name=tool_name, response=response)


def open_read_only_session(
    command: list[str],
    env: dict[str, str] | None = None,
    client_name: str = "garuda-harness",
    client_version: str = "0.1.0",
    budget: CallBudget | None = None,
    journal: EventJournal | None = None,
    run_id: str | None = None,
) -> ReadOnlySession:
    client = MCPStdioClient(command, env=env)
    client.start()

    try:
        initialized = client.request(
            "initialize",
            {
                "protocolVersion": EXPECTED_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": client_name,
                    "version": client_version,
                },
            },
        )
        result = _require_result(initialized, "initialize")
        protocol_version = result.get("protocolVersion")
        if protocol_version != EXPECTED_PROTOCOL_VERSION:
            raise ProtocolError(
                f"unsupported MCP protocol version: {protocol_version!r}; "
                f"expected {EXPECTED_PROTOCOL_VERSION!r}"
            )

        client.notify("notifications/initialized")

        tools_response = client.request("tools/list")
        tools_result = _require_result(tools_response, "tools/list")
        registry = ToolRegistry.from_tools_result(tools_result)
        registry.require_complete_read_only_surface()

        server_info = result.get("serverInfo", {})
        if not isinstance(server_info, dict):
            raise ProtocolError("initialize serverInfo must be an object")

        return ReadOnlySession(
            client=client,
            tools=registry,
            protocol_version=protocol_version,
            server_info=server_info,
            budget=budget,
            journal=journal,
            run_id=run_id,
        )
    except Exception:
        client.close()
        raise


def _require_result(response: MCPResponse, method: str) -> dict[str, Any]:
    if response.error is not None:
        raise ProtocolError(f"MCP {method} returned an error: {response.error}")
    if response.result is None:
        raise ProtocolError(f"MCP {method} returned no result")
    return response.result