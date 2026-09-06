"""Non-agent MCP and LSP protocol verification."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, BinaryIO, Protocol, cast


@dataclass(frozen=True)
class ProtocolCheck:
    ok: bool
    message: str


class JsonRpcTransport(Protocol):
    def request(self, method: str, params: dict[str, object]) -> Any: ...

    def notify(self, method: str, params: dict[str, object]) -> None: ...

    def close(self) -> None: ...


class ProcessJsonRpcTransport:
    """Small stdio JSON-RPC client supporting MCP lines and LSP headers."""

    def __init__(self, argv: Sequence[str], *, framing: str, timeout: float = 10) -> None:
        if framing not in {"line", "content-length"}:
            raise ValueError("framing must be line or content-length")
        self.framing = framing
        self.timeout = timeout
        self.next_id = 1
        self.process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

    @property
    def stdin(self) -> BinaryIO:
        if self.process.stdin is None:
            raise RuntimeError("JSON-RPC process stdin is unavailable")
        return cast(BinaryIO, self.process.stdin)

    @property
    def stdout(self) -> BinaryIO:
        if self.process.stdout is None:
            raise RuntimeError("JSON-RPC process stdout is unavailable")
        return cast(BinaryIO, self.process.stdout)

    def _write(self, message: dict[str, object]) -> None:
        body = json.dumps(message, separators=(",", ":")).encode("utf-8")
        if self.framing == "line":
            payload = body + b"\n"
        else:
            payload = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        self.stdin.write(payload)
        self.stdin.flush()

    def _read_sync(self) -> dict[str, Any]:
        if self.framing == "line":
            line = self.stdout.readline()
            if not line:
                raise RuntimeError("JSON-RPC server closed stdout")
            value = json.loads(line)
        else:
            content_length: int | None = None
            while True:
                header = self.stdout.readline()
                if not header:
                    raise RuntimeError("JSON-RPC server closed stdout")
                if header in {b"\r\n", b"\n"}:
                    break
                name, separator, raw_value = header.decode("ascii").partition(":")
                if not separator:
                    raise RuntimeError("invalid LSP response header")
                if name.lower() == "content-length":
                    content_length = int(raw_value.strip())
            if content_length is None or content_length < 0:
                raise RuntimeError("LSP response omitted Content-Length")
            value = json.loads(self.stdout.read(content_length))
        if not isinstance(value, dict):
            raise RuntimeError("JSON-RPC response must be an object")
        return value

    def _read(self) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._read_sync)
            try:
                return future.result(timeout=self.timeout)
            except FutureTimeout as exc:
                self.process.kill()
                raise RuntimeError("JSON-RPC response timed out") from exc

    def request(self, method: str, params: dict[str, object]) -> Any:
        request_id = self.next_id
        self.next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            response = self._read()
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise RuntimeError(f"JSON-RPC {method} failed: {response['error']}")
            return response.get("result")

    def notify(self, method: str, params: dict[str, object]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)


def verify_mcp_transport(transport: JsonRpcTransport, expected_product: str) -> ProtocolCheck:
    try:
        initialized = transport.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "three-layer-installer", "version": "0.1.0"},
            },
        )
        if not isinstance(initialized, dict):
            return ProtocolCheck(False, "MCP initialize returned an invalid result")
        server_info = initialized.get("serverInfo", {})
        server_name = server_info.get("name", "") if isinstance(server_info, dict) else ""
        normalized_name = str(server_name).lower().replace("-", "").replace("_", "")
        normalized_expected = expected_product.lower().replace("-", "").replace("_", "")
        if normalized_expected not in normalized_name:
            return ProtocolCheck(False, "MCP server identity did not match the expected product")
        transport.notify("notifications/initialized", {})
        tools = transport.request("tools/list", {})
        if not isinstance(tools, dict) or not isinstance(tools.get("tools"), list):
            return ProtocolCheck(False, "MCP tools/list returned an invalid result")
        if not tools["tools"]:
            return ProtocolCheck(False, "MCP server exposed no tools")
        resources = transport.request("resources/list", {})
        if not isinstance(resources, dict) or not isinstance(resources.get("resources"), list):
            return ProtocolCheck(False, "MCP resources/list returned an invalid result")
        return ProtocolCheck(True, "MCP server and tools verified")
    except Exception as exc:
        return ProtocolCheck(False, f"MCP protocol verification failed: {exc}")
    finally:
        transport.close()


def verify_mcp_server(argv: Sequence[str], expected_product: str) -> ProtocolCheck:
    try:
        transport = ProcessJsonRpcTransport(argv, framing="line")
    except OSError as exc:
        return ProtocolCheck(False, f"MCP server could not start: {exc}")
    return verify_mcp_transport(transport, expected_product)


def verify_lsp_transport(
    transport: JsonRpcTransport,
    *,
    document_uri: str,
    language_id: str,
    text: str,
) -> ProtocolCheck:
    try:
        initialized = transport.request(
            "initialize",
            {
                "processId": None,
                "rootUri": document_uri.rsplit("/", 1)[0],
                "capabilities": {},
            },
        )
        if not isinstance(initialized, dict) or not isinstance(
            initialized.get("capabilities"), dict
        ):
            return ProtocolCheck(False, "LSP initialize returned invalid capabilities")
        transport.notify("initialized", {})
        transport.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": document_uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": text,
                }
            },
        )
        position = {"line": 0, "character": 0}
        document = {"uri": document_uri}
        transport.request("textDocument/documentSymbol", {"textDocument": document})
        transport.request(
            "textDocument/definition", {"textDocument": document, "position": position}
        )
        transport.request(
            "textDocument/references",
            {
                "textDocument": document,
                "position": position,
                "context": {"includeDeclaration": True},
            },
        )
        transport.request("textDocument/hover", {"textDocument": document, "position": position})
        transport.request("shutdown", {})
        transport.notify("exit", {})
        return ProtocolCheck(True, "LSP navigation protocol verified")
    except Exception as exc:
        return ProtocolCheck(False, f"LSP protocol verification failed: {exc}")
    finally:
        transport.close()


def verify_lsp_server(
    argv: Sequence[str],
    *,
    document_uri: str,
    language_id: str,
    text: str,
) -> ProtocolCheck:
    try:
        transport = ProcessJsonRpcTransport(argv, framing="content-length")
    except OSError as exc:
        return ProtocolCheck(False, f"LSP server could not start: {exc}")
    return verify_lsp_transport(
        transport,
        document_uri=document_uri,
        language_id=language_id,
        text=text,
    )
