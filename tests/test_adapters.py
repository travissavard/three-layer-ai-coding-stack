import json
from pathlib import Path

import pytest
import tomlkit

from three_layer_installer.adapters import JMUNCH_ENV, adapter_for
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId
from three_layer_installer.paths import PathContext, PlatformKind


@pytest.fixture
def windows_context(tmp_path: Path) -> PathContext:
    return PathContext(
        PlatformKind.WINDOWS,
        tmp_path,
        {
            "APPDATA": str(tmp_path / "Roaming"),
            "LOCALAPPDATA": str(tmp_path / "Local"),
        },
    )


def test_every_client_has_a_resolvable_user_mcp_target(windows_context: PathContext) -> None:
    manifests = load_manifests()

    targets = {
        client: adapter_for(client, manifests, windows_context).mcp_target
        for client in ClientId
    }

    assert all(target.is_absolute() for target in targets.values())
    assert targets[ClientId.CLAUDE] == windows_context.home / ".claude.json"
    assert targets[ClientId.VSCODE] == (
        windows_context.home / "Roaming" / "Code" / "User" / "mcp.json"
    )


def test_standard_json_client_receives_three_pinned_servers_and_telemetry_off(
    windows_context: PathContext,
) -> None:
    adapter = adapter_for(ClientId.CLAUDE, load_manifests(), windows_context)
    updated = adapter.render_mcp('{"theme":"dark"}\n')
    parsed = json.loads(updated)

    assert parsed["theme"] == "dark"
    assert set(parsed["mcpServers"]) == {"jcodemunch", "jdocmunch", "jdatamunch"}
    assert parsed["mcpServers"]["jcodemunch"]["args"] == [
        "--from",
        "jcodemunch-mcp==1.108.317",
        "jcodemunch-mcp",
    ]
    assert parsed["mcpServers"]["jcodemunch"]["env"] == JMUNCH_ENV


def test_kilo_uses_local_jsonc_command_array(windows_context: PathContext) -> None:
    adapter = adapter_for(ClientId.KILO, load_manifests(), windows_context)

    updated = adapter.render_mcp("{\n  // user setting\n  \"theme\": \"dark\",\n}\n")

    assert "// user setting" in updated
    assert '"type": "local"' in updated
    assert '"command": [' in updated
    assert '"environment"' in updated


def test_codex_uses_absolute_managed_executables(windows_context: PathContext) -> None:
    adapter = adapter_for(ClientId.CODEX, load_manifests(), windows_context)
    updated = adapter.render_mcp('# keep\nmodel = "example"\n')
    parsed = tomlkit.parse(updated)

    command = parsed["mcp_servers"]["jcodemunch"]["command"]
    assert Path(command).is_absolute()
    assert command.endswith("jcodemunch-mcp.exe")
    assert "# keep" in updated


def test_project_path_is_used_only_when_client_documents_it(
    windows_context: PathContext, tmp_path: Path
) -> None:
    vscode = adapter_for(ClientId.VSCODE, load_manifests(), windows_context, tmp_path)
    claude = adapter_for(ClientId.CLAUDE, load_manifests(), windows_context, tmp_path)

    assert vscode.mcp_target == tmp_path / ".vscode" / "mcp.json"
    assert claude.mcp_target == windows_context.home / ".claude.json"


def test_unavailable_client_has_no_lsp_target(windows_context: PathContext) -> None:
    codex = adapter_for(ClientId.CODEX, load_manifests(), windows_context)

    assert codex.lsp_target is None
    assert codex.render_lsp("{}", ("python",)) is None


def test_qwen_lsp_requires_and_writes_selected_project(
    windows_context: PathContext, tmp_path: Path
) -> None:
    qwen = adapter_for(ClientId.QWEN, load_manifests(), windows_context, tmp_path)
    updated = qwen.render_lsp("{}\n", ("python",))

    assert qwen.lsp_target == tmp_path / ".lsp.json"
    assert updated is not None
    assert json.loads(updated)["python"]["command"] == "pyright-langserver"


def test_claude_uses_official_lsp_plugins(windows_context: PathContext) -> None:
    claude = adapter_for(ClientId.CLAUDE, load_manifests(), windows_context)

    assert claude.lsp_commands(("typescript", "python", "rust")) == (
        (
            "claude",
            "plugin",
            "install",
            "typescript-lsp@claude-plugins-official",
            "--scope",
            "user",
        ),
        ("claude", "plugin", "install", "pyright-lsp@claude-plugins-official", "--scope", "user"),
        (
            "claude",
            "plugin",
            "install",
            "rust-analyzer-lsp@claude-plugins-official",
            "--scope",
            "user",
        ),
    )
