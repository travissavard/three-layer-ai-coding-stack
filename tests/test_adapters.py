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
    assert targets[ClientId.KILO] == windows_context.home / ".config" / "kilo" / "kilo.jsonc"
    assert targets[ClientId.KIMI] == windows_context.home / ".kimi" / "mcp.json"
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


def test_copilot_uses_its_documented_local_server_shape(
    windows_context: PathContext,
) -> None:
    adapter = adapter_for(ClientId.COPILOT, load_manifests(), windows_context)

    configured = json.loads(adapter.render_mcp("{}\n"))["mcpServers"]["jcodemunch"]

    assert configured["type"] == "local"
    assert configured["tools"] == ["*"]


def test_vscode_uses_explicit_stdio_transport(windows_context: PathContext) -> None:
    adapter = adapter_for(ClientId.VSCODE, load_manifests(), windows_context)

    configured = json.loads(adapter.render_mcp("{}\n"))["servers"]["jcodemunch"]

    assert configured["type"] == "stdio"


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


def test_kilo_uses_documented_clean_project_config_when_project_is_selected(
    windows_context: PathContext, tmp_path: Path
) -> None:
    kilo = adapter_for(ClientId.KILO, load_manifests(), windows_context, tmp_path)

    assert kilo.mcp_target == tmp_path / ".kilo" / "kilo.jsonc"
    assert kilo.lsp_target == kilo.mcp_target


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
    configured = json.loads(updated)["python"]
    assert configured["command"] == "pyright-langserver"
    assert configured["extensionToLanguage"] == {".py": "python", ".pyi": "python"}


def test_copilot_lsp_uses_file_extension_language_map(
    windows_context: PathContext,
) -> None:
    copilot = adapter_for(ClientId.COPILOT, load_manifests(), windows_context)

    updated = copilot.render_lsp("{}\n", ("typescript",))

    assert updated is not None
    configured = json.loads(updated)["lspServers"]["typescript"]
    assert configured["fileExtensions"][".tsx"] == "typescriptreact"


def test_kiro_lsp_uses_documented_languages_schema(
    windows_context: PathContext, tmp_path: Path
) -> None:
    kiro = adapter_for(ClientId.KIRO, load_manifests(), windows_context, tmp_path)

    updated = kiro.render_lsp("{}\n", ("go",))

    assert updated is not None
    configured = json.loads(updated)["languages"]["go"]
    assert configured == {
        "name": "gopls",
        "command": "gopls",
        "args": ["serve"],
        "file_extensions": ["go"],
    }


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
