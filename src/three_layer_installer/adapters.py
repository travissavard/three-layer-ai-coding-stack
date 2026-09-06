"""Client-specific configuration shapes over shared safe editors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .config_edit import set_jsonc_path, set_toml_path
from .manifests import ManifestSet
from .models import ClientId
from .paths import PathContext, configured_path_templates

JMUNCH_ENV = {
    "JCODEMUNCH_SHARE_SAVINGS": "0",
    "JDOCMUNCH_SHARE_SAVINGS": "0",
    "JDATAMUNCH_SHARE_SAVINGS": "0",
}

_CLAUDE_LSP_PLUGINS = {
    "typescript": "typescript-lsp@claude-plugins-official",
    "python": "pyright-lsp@claude-plugins-official",
    "rust": "rust-analyzer-lsp@claude-plugins-official",
}


@dataclass(frozen=True)
class ClientAdapter:
    client_id: ClientId
    manifests: ManifestSet
    context: PathContext
    project: Path | None = None
    uvx_command: str = "uvx"
    latest: bool = False

    @property
    def definition(self) -> dict[str, object]:
        return cast(dict[str, object], self.manifests.clients["clients"][self.client_id.value])

    @property
    def mcp_target(self) -> Path:
        mcp = self.definition["mcp"]
        if not isinstance(mcp, dict):
            raise ValueError(f"{self.client_id.value} has no MCP configuration")
        project_path = mcp.get("project_path")
        if self.project is not None and isinstance(project_path, str):
            return (self.project / project_path).resolve()
        templates = configured_path_templates(self.definition, self.context.platform)
        if not templates:
            raise ValueError(f"{self.client_id.value} has no MCP path for this platform")
        if self.client_id is ClientId.KIMI:
            existing = [
                self.context.resolve(item)
                for item in templates
                if self.context.resolve(item).exists()
            ]
            if existing:
                return existing[0]
        return self.context.resolve(templates[0]).resolve()

    def _managed_command(self, component: str) -> str:
        tool = self.manifests.versions["tools"][component]
        executable = tool["executable"]
        if self.context.platform.value == "windows":
            executable += ".exe"
        return str(
            (
                self.context.state_root
                / "tools"
                / "jmunch"
                / component
                / ("latest" if self.latest else tool["version"])
                / "bin"
                / executable
            ).resolve()
        )

    def jmunch_entries(self) -> dict[str, dict[str, object]]:
        entries: dict[str, dict[str, object]] = {}
        for component in ("jcodemunch", "jdocmunch", "jdatamunch"):
            tool = self.manifests.versions["tools"][component]
            if self.client_id is ClientId.CODEX:
                entry: dict[str, object] = {
                    "command": self._managed_command(component),
                    "env": dict(JMUNCH_ENV),
                }
            else:
                command = [
                    self.uvx_command,
                    "--from",
                    (
                        str(tool["package"])
                        if self.latest
                        else f"{tool['package']}=={tool['version']}"
                    ),
                    tool["executable"],
                ]
                if self.client_id is ClientId.KILO:
                    entry = {
                        "type": "local",
                        "command": command,
                        "environment": dict(JMUNCH_ENV),
                        "enabled": True,
                    }
                else:
                    entry = {
                        "command": command[0],
                        "args": command[1:],
                        "env": dict(JMUNCH_ENV),
                    }
                    if self.client_id is ClientId.COPILOT:
                        entry.update({"type": "local", "tools": ["*"]})
                    elif self.client_id is ClientId.VSCODE:
                        entry["type"] = "stdio"
            entries[component] = entry
        return entries

    def render_mcp(self, existing: str) -> str:
        mcp = self.definition["mcp"]
        if not isinstance(mcp, dict):
            raise ValueError(f"{self.client_id.value} has no MCP configuration")
        root_key = mcp["root_key"]
        if not isinstance(root_key, str):
            raise ValueError(f"{self.client_id.value} has an invalid MCP root key")
        format_name = mcp["format"]
        updated = existing if existing.strip() else ("" if format_name == "toml" else "{}\n")
        for component, entry in self.jmunch_entries().items():
            path = (root_key, component)
            if format_name == "toml":
                updated = set_toml_path(updated, path, entry)
            else:
                updated = set_jsonc_path(updated, path, entry)
        return updated

    @property
    def lsp_target(self) -> Path | None:
        lsp = self.definition["lsp"]
        if not isinstance(lsp, dict) or lsp["classification"] in {"unavailable", "editor"}:
            return None
        if self.client_id is ClientId.CLAUDE:
            return None
        path = lsp.get("path")
        if isinstance(path, str):
            return (self.project / path).resolve() if self.project else None
        if self.client_id is ClientId.COPILOT:
            return self.context.resolve("~/.copilot/lsp-config.json").resolve()
        if self.client_id is ClientId.KILO:
            return self.mcp_target
        return None

    def render_lsp(self, existing: str, languages: tuple[str, ...]) -> str | None:
        target = self.lsp_target
        if target is None:
            return None
        updated = existing if existing.strip() else "{}\n"
        for language in languages:
            definition = self.manifests.languages["languages"][language]
            command = definition["command"]
            language_ids = definition["language_ids"]
            root: tuple[str, ...]
            if self.client_id is ClientId.QWEN:
                root = ()
                entry = {
                    "command": command[0],
                    "args": command[1:],
                    "extensionToLanguage": language_ids,
                }
            elif self.client_id is ClientId.KILO:
                root = ("lsp",)
                entry = {"command": command, "extensions": definition["extensions"]}
            elif self.client_id is ClientId.KIRO:
                root = ("languages",)
                entry = {
                    "name": definition["server"],
                    "command": command[0],
                    "args": command[1:],
                    "file_extensions": [
                        extension.removeprefix(".") for extension in definition["extensions"]
                    ],
                }
            else:
                root = ("lspServers",)
                entry = {
                    "command": command[0],
                    "args": command[1:],
                    "fileExtensions": language_ids,
                }
            updated = set_jsonc_path(updated, (*root, language), entry)
        return updated

    def lsp_commands(self, languages: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
        if self.client_id is not ClientId.CLAUDE:
            return ()
        return tuple(
            ("claude", "plugin", "install", plugin, "--scope", "user")
            for language in languages
            if (plugin := _CLAUDE_LSP_PLUGINS.get(language)) is not None
        )


def adapter_for(
    client_id: ClientId,
    manifests: ManifestSet,
    context: PathContext,
    project: Path | None = None,
    uvx_command: str = "uvx",
    latest: bool = False,
) -> ClientAdapter:
    return ClientAdapter(
        client_id,
        manifests,
        context,
        project.resolve() if project else None,
        uvx_command,
        latest,
    )
