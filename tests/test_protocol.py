import sys

import pytest

from harness.errors import ProtocolError, TransportError
from harness.protocol import MCPStdioClient

FAKE_SERVER = r"""
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue

    method = request["method"]
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "serverInfo": {"name": "fake-garuda-mcp"},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": "garuda.entities"},
                {"name": "garuda.policy.evaluate"},
            ]
        }
    else:
        result = {}

    sys.stdout.write(json.dumps({
        "jsonrpc": "2.0",
        "id": request["id"],
        "result": result,
    }) + "\n")
    sys.stdout.flush()
"""


def fake_command() -> list[str]:
    return [sys.executable, "-u", "-c", FAKE_SERVER]


def test_initialize_and_tools_list() -> None:
    client = MCPStdioClient(fake_command())
    client.start()
    try:
        initialized = client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "garuda-harness", "version": "0.1.0"},
            },
        )
        assert initialized.error is None
        assert initialized.result is not None
        assert initialized.result["protocolVersion"] == "2025-06-18"

        client.notify("notifications/initialized")

        tools = client.request("tools/list")
        assert tools.error is None
        assert tools.result is not None
        assert len(tools.result["tools"]) == 2
    finally:
        assert client.close() == 0


def test_request_before_start_fails() -> None:
    client = MCPStdioClient(fake_command())

    with pytest.raises(TransportError):
        client.request("tools/list")


def test_invalid_json_response_fails() -> None:
    bad_server = "import sys; print('not-json', flush=True)"
    client = MCPStdioClient([sys.executable, "-u", "-c", bad_server])
    client.start()

    try:
        with pytest.raises(ProtocolError):
            client.request("initialize")
    finally:
        client.close()


def test_notification_has_no_response() -> None:
    client = MCPStdioClient(fake_command())
    client.start()

    try:
        client.notify("notifications/initialized")
    finally:
        assert client.close() == 0
