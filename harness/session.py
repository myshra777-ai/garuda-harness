"""Read-only MCP session bootstrap for H1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ProtocolError
from .protocol import MCPResponse, MCPStdioClient
from .tools import ToolRegistry

EXPECTED_PROTOCOL_VERSION = "2025-06-18"


@dataclass
class ReadOnlySession:
    client: MCPStdioClient
    tools: ToolRegistry
    protocol_version: str
    server_info: dict[str, Any]

    def close(self) -> int:
        return self.client.close()

    def call_read_only(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPResponse:
        self.tools.require_read_only(tool_name)
        return self.client.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {},
            },
        )


def open_read_only_session(
    command: list[str],
    env: dict[str, str] | None = None,
    client_name: str = "garuda-harness",
    client_version: str = "0.1.0",
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
