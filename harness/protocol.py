"""Bounded JSON-RPC stdio client for the Garuda MCP server."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from .errors import ProtocolError, TransportError


@dataclass(frozen=True)
class MCPResponse:
    identifier: int | str | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None


class MCPStdioClient:
    def __init__(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = command
        self._env = env
        self._process: subprocess.Popen[bytes] | None = None
        self._next_id = 1

    def start(self) -> None:
        if self._process is not None:
            raise TransportError("MCP process is already running")

        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env,
            )
        except OSError as exc:
            raise TransportError(f"failed to start MCP process: {exc}") from exc

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> MCPResponse:
        process = self._require_process()

        if process.stdin is None or process.stdout is None:
            raise TransportError("MCP process pipes are unavailable")

        identifier = self._next_id
        self._next_id += 1

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        wire = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
        try:
            process.stdin.write(wire)
            process.stdin.flush()
            line = process.stdout.readline()
        except OSError as exc:
            raise TransportError(f"MCP stdio failure: {exc}") from exc

        if not line:
            raise TransportError("MCP process closed stdout unexpectedly")

        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid MCP JSON response: {line!r}") from exc

        if not isinstance(response, dict):
            raise ProtocolError("MCP response must be a JSON object")

        if response.get("jsonrpc") != "2.0":
            raise ProtocolError("MCP response has invalid jsonrpc version")

        if response.get("id") != identifier:
            raise ProtocolError(
                f"MCP response ID {response.get('id')!r} does not match "
                f"request ID {identifier!r}"
            )

        return MCPResponse(
            identifier=response.get("id"),
            result=response.get("result"),
            error=response.get("error"),
        )

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        process = self._require_process()

        if process.stdin is None:
            raise TransportError("MCP process stdin is unavailable")

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        wire = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
        try:
            process.stdin.write(wire)
            process.stdin.flush()
        except OSError as exc:
            raise TransportError(f"MCP notification failure: {exc}") from exc

    def close(self) -> int:
        process = self._process
        if process is None:
            return 0

        if process.stdin is not None:
            process.stdin.close()

        return_code = process.wait(timeout=5)
        self._process = None
        return return_code

    def _require_process(self) -> subprocess.Popen[bytes]:
        if self._process is None:
            raise TransportError("MCP process has not been started")
        return self._process
