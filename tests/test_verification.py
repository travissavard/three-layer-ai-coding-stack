from typing import Any

from three_layer_installer.verification import (
    ProtocolCheck,
    verify_lsp_transport,
    verify_mcp_transport,
)


class FakeTransport:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.requests: list[str] = []
        self.notifications: list[str] = []

    def request(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        del params
        self.requests.append(method)
        value = self.responses[method]
        if isinstance(value, Exception):
            raise value
        return value

    def notify(self, method: str, params: dict[str, object]) -> None:
        del params
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


def test_lsp_verification_surfaces_protocol_failure_and_closes_transport() -> None:
    transport = FakeTransport({"initialize": RuntimeError("fixture protocol error")})

    result = verify_lsp_transport(
        transport,
        document_uri="file:///fixture/example.go",
        language_id="go",
        text="package fixture\n",
    )

    assert result.ok is False
    assert "fixture protocol error" in result.message
    assert transport.notifications[-1] == "closed"
