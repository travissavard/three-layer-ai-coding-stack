"""Read-only verification of configured stack components."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from .adapters import JMUNCH_ENV, ClientAdapter, adapter_for
from .config_edit import ConfigError, read_config
from .executor import CommandRunner, SubprocessRunner
from .manifests import ManifestSet
from .models import (
    ClientId,
    InstallPlan,
    Layer,
    LayerResult,
    Status,
    VerificationScope,
)
from .paths import PathContext
from .tooling import resolve_toolchain
from .verification import ProtocolCheck, verify_lsp_server, verify_mcp_server

McpVerifier = Callable[..., ProtocolCheck]
LspVerifier = Callable[..., ProtocolCheck]

_FIXTURES = {
    "typescript": ("example.ts", "typescript", "const value = 1;\n"),
    "python": ("example.py", "python", "value = 1\n"),
    "rust": ("main.rs", "rust", "fn main() {}\n"),
    "go": ("main.go", "go", "package main\nfunc main() {}\n"),
}


def _projected(plan: InstallPlan, client: ClientId, layer: Layer) -> LayerResult:
    return next(
        result
        for result in plan.results
        if result.client is client and result.layer is layer
    )


def _verify_rtk(
    projected: LayerResult,
    runner: CommandRunner,
    cached: ProtocolCheck | None,
    rtk_command: str,
    adapter: ClientAdapter,
) -> tuple[LayerResult, ProtocolCheck | None]:
    if projected.status is Status.SKIPPED:
        return projected, cached
    if cached is None:
        result = runner.run((rtk_command, "gain"), timeout=15)
        cached = ProtocolCheck(
            result.returncode == 0,
            "RTK identity and gain command verified" if result.returncode == 0
            else "RTK gain failed; check that the RTK executable is installed",
        )
    definition = adapter.definition["rtk"]
    assert isinstance(definition, dict)
    templates = []
    if definition["mode"] == "guidance":
        templates.append(definition["path"])
    else:
        owned = definition["owned_paths"]
        for key in ("all", adapter.context.platform.value, "project"):
            templates.extend(owned.get(key, []))
    required = []
    for template in templates:
        path = adapter.context.resolve(template)
        if not path.is_absolute() and adapter.project is not None:
            path = adapter.project / path
        if path.suffix in {".md", ".json"}:
            required.append(path)
    try:
        configured = bool(required) and all(
            path.is_file() and "rtk" in path.read_text(encoding="utf-8-sig").lower()
            for path in required
        )
    except (OSError, UnicodeError):
        configured = False
    return (
        LayerResult(
            projected.client,
            Layer.RTK,
            projected.status if cached.ok and configured else Status.FAILED,
            (
                f"{cached.message}; client integration remains {projected.status.value}"
                if cached.ok and configured
                else "RTK integration files are missing or incomplete" if cached.ok
                else cached.message
            ),
            verification_scope=VerificationScope.SERVER_PROTOCOL,
        ),
        cached,
    )


def _verify_lsp(
    projected: LayerResult,
    plan: InstallPlan,
    manifests: ManifestSet,
    adapter: ClientAdapter,
    which: Callable[[str], str | None],
    verifier: LspVerifier,
) -> LayerResult:
    if projected.status in {Status.SKIPPED, Status.UNAVAILABLE_FROM_CLIENT}:
        return projected
    classification = adapter.definition["lsp"]
    if isinstance(classification, dict) and classification.get("classification") == "editor":
        return projected
    component_status: dict[str, Status] = {}
    messages: list[str] = []
    selected_languages = tuple(
        language
        for language, status in projected.components.items()
        if status is not Status.SKIPPED
    )
    if not selected_languages:
        selected_languages = plan.languages
    try:
        if adapter.client_id is ClientId.CLAUDE:
            settings = adapter.context.resolve("${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json")
            document = read_config(settings.read_text(encoding="utf-8-sig"))
            plugins = document.get("enabledPlugins", {})
            configured = isinstance(plugins, dict) and all(
                plugins.get(command[3]) is True
                for command in adapter.lsp_commands(selected_languages)
            )
        else:
            target = adapter.lsp_target
            rendered = adapter.render_lsp("{}", selected_languages)
            configured = target is not None and rendered is not None and _contains(
                read_config(target.read_text(encoding="utf-8-sig")), read_config(rendered)
            )
    except (OSError, UnicodeError, ConfigError):
        configured = False
    if not configured:
        return LayerResult(
            projected.client, Layer.LSP, Status.FAILED,
            "Native LSP configuration is missing or differs from the selected language packs",
            verification_scope=VerificationScope.CONFIG_ONLY,
        )
    with tempfile.TemporaryDirectory(prefix="three-layer-lsp-") as temporary:
        # gopls rejects Windows short-name aliases (for example RUNNER~1).
        temporary_root = Path(temporary).resolve()
        for language in selected_languages:
            definition = manifests.languages["languages"][language]
            command = tuple(definition["command"])
            if which(command[0]) is None:
                component_status[language] = Status.FAILED
                messages.append(f"{language} server executable was not found")
                continue
            filename, language_id, text = _FIXTURES[language]
            fixture = temporary_root / filename
            fixture.write_text(text, encoding="utf-8")
            check = verifier(
                command,
                document_uri=fixture.as_uri(),
                language_id=language_id,
                text=text,
            )
            component_status[language] = Status.ACTIVE if check.ok else Status.FAILED
            if not check.ok:
                messages.append(f"{language}: {check.message}")
    passed = component_status and all(
        status is Status.ACTIVE for status in component_status.values()
    )
    status = projected.status if passed else Status.FAILED
    message = (
        f"Language-server protocol verified; client integration remains {projected.status.value}"
        if passed
        else "; ".join(messages)
    )
    return LayerResult(
        projected.client,
        Layer.LSP,
        status,
        message,
        components=component_status,
        verification_scope=VerificationScope.SERVER_PROTOCOL,
    )


def _entry_argv(entry: dict[str, object]) -> tuple[str, ...]:
    command = entry["command"]
    if isinstance(command, list):
        return tuple(str(item) for item in command)
    args = entry.get("args", [])
    if not isinstance(args, list):
        return (str(command),)
    return (str(command), *(str(item) for item in args))


def _contains(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value)
            for key, value in expected.items()
        )
    return actual == expected


def _verify_jmunch(
    projected: LayerResult,
    adapter: ClientAdapter,
    verifier: McpVerifier,
) -> LayerResult:
    if projected.status is Status.SKIPPED:
        return projected
    definition = adapter.definition["mcp"]
    assert isinstance(definition, dict)
    try:
        document = read_config(
            adapter.mcp_target.read_text(encoding="utf-8-sig"), definition["format"]
        )
        saved = document.get(definition["root_key"], {})
    except (OSError, UnicodeError, ConfigError):
        saved = None
    if not isinstance(saved, dict):
        failed = {component: Status.FAILED for component in adapter.jmunch_entries()}
        return LayerResult(
            projected.client,
            Layer.JMUNCH,
            Status.FAILED,
            "MCP configuration is missing or invalid",
            components=failed,
            verification_scope=VerificationScope.CONFIG_ONLY,
        )
    statuses: dict[str, Status] = {}
    messages: list[str] = []
    for component, entry in adapter.jmunch_entries().items():
        actual = saved.get(component)
        if (
            not isinstance(actual, dict) or not _contains(actual, entry)
            or actual.get("disabled") is True or actual.get("enabled") is False
        ):
            statuses[component] = Status.FAILED
            messages.append(f"{component}: saved MCP entry is missing, disabled, or differs")
            continue
        check = verifier(_entry_argv(entry), component, environment=JMUNCH_ENV)
        statuses[component] = Status.ACTIVE if check.ok else Status.FAILED
        if not check.ok:
            messages.append(f"{component}: {check.message}")
    passed = all(status is Status.ACTIVE for status in statuses.values())
    return LayerResult(
        projected.client,
        Layer.JMUNCH,
        Status.ACTIVE if passed else Status.FAILED,
        "Saved configuration and all three MCP servers verified; restart the client"
        if passed else "; ".join(messages),
        components=statuses,
        verification_scope=VerificationScope.SERVER_PROTOCOL,
    )


def verify_stack(
    plan: InstallPlan,
    manifests: ManifestSet,
    context: PathContext,
    *,
    runner: CommandRunner | None = None,
    which: Callable[[str], str | None] = shutil.which,
    mcp_verifier: McpVerifier = verify_mcp_server,
    lsp_verifier: LspVerifier = verify_lsp_server,
) -> tuple[LayerResult, ...]:
    command_runner = runner or SubprocessRunner()
    toolchain = resolve_toolchain(
        context,
        which=which,
        latest_rtk=plan.options.latest,
    )
    results: list[LayerResult] = []
    rtk_check: ProtocolCheck | None = None
    for client in plan.selected_clients:
        adapter = adapter_for(
            client,
            manifests,
            context,
            plan.options.project,
            toolchain.uvx_command or "uvx",
            plan.options.latest,
        )
        rtk_result, rtk_check = _verify_rtk(
            _projected(plan, client, Layer.RTK),
            command_runner,
            rtk_check,
            toolchain.rtk_command,
            adapter,
        )
        results.append(rtk_result)
        results.append(
            _verify_lsp(
                _projected(plan, client, Layer.LSP),
                plan,
                manifests,
                adapter,
                which,
                lsp_verifier,
            )
        )
        results.append(
            _verify_jmunch(_projected(plan, client, Layer.JMUNCH), adapter, mcp_verifier)
        )
    return tuple(results)
