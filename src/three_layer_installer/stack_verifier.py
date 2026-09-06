"""Read-only verification of configured stack components."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from .adapters import ClientAdapter, adapter_for
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

McpVerifier = Callable[[Sequence[str], str], ProtocolCheck]
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
) -> tuple[LayerResult, ProtocolCheck | None]:
    if projected.status is Status.SKIPPED:
        return projected, cached
    if cached is None:
        result = runner.run((rtk_command, "gain"), timeout=15)
        cached = ProtocolCheck(result.returncode == 0, "RTK identity and gain command verified")
    return (
        LayerResult(
            projected.client,
            Layer.RTK,
            Status.ACTIVE if cached.ok else Status.FAILED,
            cached.message,
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
    with tempfile.TemporaryDirectory(prefix="three-layer-lsp-") as temporary:
        temporary_root = Path(temporary)
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
    status = (
        Status.EXPERIMENTAL
        if passed and projected.status is Status.EXPERIMENTAL
        else (Status.ACTIVE if passed else Status.FAILED)
    )
    message = "Language-server protocol verified" if passed else "; ".join(messages)
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


def _verify_jmunch(
    projected: LayerResult,
    adapter: ClientAdapter,
    verifier: McpVerifier,
) -> LayerResult:
    if projected.status is Status.SKIPPED:
        return projected
    if not adapter.mcp_target.is_file():
        failed = {component: Status.FAILED for component in adapter.jmunch_entries()}
        return LayerResult(
            projected.client,
            Layer.JMUNCH,
            Status.FAILED,
            f"MCP configuration was not found at {adapter.mcp_target}",
            components=failed,
            verification_scope=VerificationScope.CONFIG_ONLY,
        )
    statuses: dict[str, Status] = {}
    messages: list[str] = []
    for component, entry in adapter.jmunch_entries().items():
        check = verifier(_entry_argv(entry), component)
        statuses[component] = Status.ACTIVE if check.ok else Status.FAILED
        if not check.ok:
            messages.append(f"{component}: {check.message}")
    passed = all(status is Status.ACTIVE for status in statuses.values())
    return LayerResult(
        projected.client,
        Layer.JMUNCH,
        Status.ACTIVE if passed else Status.FAILED,
        "All three MCP servers verified" if passed else "; ".join(messages),
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
    toolchain = resolve_toolchain(context, which=which)
    results: list[LayerResult] = []
    rtk_check: ProtocolCheck | None = None
    for client in plan.selected_clients:
        adapter = adapter_for(
            client,
            manifests,
            context,
            plan.options.project,
            toolchain.uvx_command or "uvx",
        )
        rtk_result, rtk_check = _verify_rtk(
            _projected(plan, client, Layer.RTK),
            command_runner,
            rtk_check,
            toolchain.rtk_command,
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
