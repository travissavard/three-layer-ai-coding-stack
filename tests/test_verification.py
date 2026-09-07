import sys
from typing import Any

import pytest

from three_layer_installer.verification import (
    ProcessJsonRpcTransport,
    ProtocolCheck,
    verify_lsp_transport,
    verify_mcp_transport,
)


class FakeTransport:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.requests: list[str] = []
        self.notifications: list[str] = []
        self.request_params: dict[str, dict[str, object] | None] = {}
        self.notification_params: dict[str, dict[str, object] | None] = {}

    def request(self, method: str, params: dict[str, object] | None) -> Any:
        self.request_params[method] = params
        self.requests.append(method)
        value = self.responses[method]
        if isinstance(value, Exception):
            raise value
        return value

    def notify(self, method: str, params: dict[str, object] | None) -> None:
        self.notification_params[method] = params
        self.notifications.append(method)

    def close(self) -> None:
        self.notifications.append("closed")


def test_mcp_verification_initializes_and_lists_tools_without_indexing() -> None:
    transport = FakeTransport(
        {
            "initialize": {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "jcodemunch-mcp", "version": "1.0"},
            },
            "tools/list": {"tools": [{"name": "search_symbols"}]},
            "resources/list": {"resources": []},
        }
    )

    result = verify_mcp_transport(transport, "jcodemunch")

    assert result == ProtocolCheck(True, "MCP server and tools verified")
    assert transport.requests == ["initialize", "tools/list", "resources/list"]
    assert "notifications/initialized" in transport.notifications
    assert not any("index" in method for method in transport.requests)


def test_mcp_verification_rejects_empty_tool_inventory() -> None:
    transport = FakeTransport(
        {
            "initialize": {"serverInfo": {"name": "jdocmunch"}},
            "tools/list": {"tools": []},
            "resources/list": {"resources": []},
        }
    )

    result = verify_mcp_transport(transport, "jdocmunch")

    assert result.ok is False
    assert "no tools" in result.message


def test_mcp_verification_rejects_wrong_product_identity() -> None:
    transport = FakeTransport(
        {
            "initialize": {"serverInfo": {"name": "unrelated-server"}},
            "tools/list": {"tools": [{"name": "something"}]},
            "resources/list": {"resources": []},
        }
    )

    result = verify_mcp_transport(transport, "jdatamunch")

    assert result.ok is False
    assert "identity" in result.message


def test_lsp_verification_exercises_navigation_and_shutdown() -> None:
    transport = FakeTransport(
        {
            "initialize": {"capabilities": {"definitionProvider": True}},
            "textDocument/documentSymbol": [],
            "textDocument/definition": None,
            "textDocument/references": [],
            "textDocument/hover": None,
            "shutdown": None,
        }
    )

    result = verify_lsp_transport(
        transport,
        document_uri="file:///fixture/example.py",
        language_id="python",
        text="value = 1\n",
    )

    assert result.ok is True
    assert transport.requests == [
        "initialize",
        "textDocument/documentSymbol",
        "textDocument/definition",
        "textDocument/references",
        "textDocument/hover",
        "shutdown",
    ]
    assert transport.notifications == ["initialized", "textDocument/didOpen", "exit", "closed"]
    assert transport.request_params["shutdown"] is None
    assert transport.notification_params["exit"] is None


def test_lsp_verification_surfaces_protocol_failure_and_closes_transport() -> None:
    transport = FakeTransport({"initialize": RuntimeError("fixture protocol error")})

    result = verify_lsp_transport(
        transport,
        document_uri="file:///fixture/example.go",
        language_id="go",
        text="package fixture\n",
    )

    assert result.ok is False
    assert "RuntimeError" in result.message
    assert "fixture protocol error" not in result.message
    assert transport.notifications[-1] == "closed"


@pytest.mark.parametrize("framing", ["line", "content-length"])
def test_real_stdio_transport_frames_messages_and_passes_environment(framing: str) -> None:
    server = r"""
import json, os, sys
framing = sys.argv[1]
if framing == 'line':
    request = json.loads(sys.stdin.buffer.readline())
else:
    length = int(sys.stdin.buffer.readline().split(b':')[1])
    sys.stdin.buffer.readline()
    request = json.loads(sys.stdin.buffer.read(length))
body = json.dumps({'jsonrpc': '2.0', 'id': request['id'],
                   'result': os.environ['TRANSPORT_FIXTURE']}).encode()
payload = body + b'\n' if framing == 'line' else (
    ('Content-Length: %d\r\n\r\n' % len(body)).encode() + body)
sys.stdout.buffer.write(payload)
sys.stdout.buffer.flush()
sys.stdin.buffer.read()
"""
    transport = ProcessJsonRpcTransport(
        (sys.executable, "-u", "-c", server, framing),
        framing=framing,
        environment={"TRANSPORT_FIXTURE": "fixture-value"},
    )
    try:
        assert transport.request("fixture", {}) == "fixture-value"
        transport.notify("exit", {})
    finally:
        transport.close()
    assert transport.process.poll() is not None


def test_real_stdio_transport_times_out_and_reaps_server() -> None:
    transport = ProcessJsonRpcTransport(
        (sys.executable, "-c", "import time; time.sleep(5)"),
        framing="line",
        timeout=0.1,
    )
    try:
        with pytest.raises(RuntimeError, match="timed out"):
            transport.request("fixture", {})
    finally:
        transport.close()
    assert transport.process.poll() is not None


@pytest.mark.parametrize("payload", ["[]", '{"id":1,"error":"fixture-secret"}'])
def test_real_stdio_transport_rejects_bad_response_without_echoing_contents(payload: str) -> None:
    transport = ProcessJsonRpcTransport(
        (
            sys.executable,
            "-u",
            "-c",
            "import sys; sys.stdin.readline(); print(sys.argv[1])",
            payload,
        ),
        framing="line",
    )
    try:
        with pytest.raises(RuntimeError) as error:
            transport.request("fixture", {})
        assert "fixture-secret" not in str(error.value)
    finally:
        transport.close()
