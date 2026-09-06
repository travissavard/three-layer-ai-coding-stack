"""Apply a confirmed install plan without invoking a shell."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .adapters import ClientAdapter, adapter_for
from .backup import BackupManager, BackupOperation, atomic_write
from .config_edit import set_owned_block
from .manifests import ManifestSet
from .models import ClientId, InstallPlan, Layer, LayerResult
from .paths import PathContext
from .tooling import (
    ToolBootstrapError,
    Toolchain,
    install_verified_rtk,
    materialize_bootstrap_uv,
    resolve_toolchain,
)


class ExecutionError(RuntimeError):
    """A confirmed action failed and cannot safely continue."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 60,
    ) -> CommandResult: ...


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        process_environment = dict(os.environ)
        if environment:
            process_environment.update(environment)
        try:
            completed = subprocess.run(
                list(argv),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=process_environment,
                shell=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return CommandResult(127, "", type(exc).__name__)
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True)
class ExecutionReport:
    operation_id: str | None
    results: tuple[LayerResult, ...]


def _run_required(
    runner: CommandRunner,
    argv: tuple[str, ...],
    description: str,
    *,
    environment: Mapping[str, str] | None = None,
    timeout: float = 60,
) -> None:
    result = runner.run(argv, environment=environment, timeout=timeout)
    if result.returncode != 0:
        raise ExecutionError(f"{description} failed (exit {result.returncode})")


def _rtk_preflight(plan: InstallPlan, runner: CommandRunner, rtk_command: str) -> None:
    native = [action for action in plan.actions if action.kind == "rtk-native"]
    if not any(action.layer is Layer.RTK for action in plan.actions):
        return
    identity = runner.run((rtk_command, "gain"), timeout=15)
    if identity.returncode != 0:
        raise ExecutionError(
            "RTK identity check failed; refusing to use an executable that may be Rust Type Kit"
        )
    for action in native:
        if not action.argv or action.argv[0] != "init":
            raise ExecutionError("RTK manifest contains an invalid initialization command")
        preview = (rtk_command, "init", "--dry-run", *action.argv[1:])
        _run_required(runner, preview, f"RTK preflight for {action.client.value}")
        _run_required(
            runner,
            (rtk_command, *action.argv),
            f"RTK setup for {action.client.value}",
        )


def _guidance_target(adapter: ClientAdapter) -> Path | None:
    rtk = adapter.definition.get("rtk")
    if not isinstance(rtk, dict) or rtk.get("mode") != "guidance":
        return None
    value = rtk.get("path")
    return adapter.context.resolve(value).resolve() if isinstance(value, str) else None


def _target_paths(
    plan: InstallPlan,
    adapters: dict[ClientId, ClientAdapter],
    toolchain: Toolchain,
) -> tuple[Path, ...]:
    paths: list[Path] = list(toolchain.managed_targets)
    for client_id in plan.selected_clients:
        adapter = adapters[client_id]
        client_actions = [action for action in plan.actions if action.client is client_id]
        if any(action.layer is Layer.JMUNCH for action in client_actions):
            paths.append(adapter.mcp_target)
        if any(action.layer is Layer.LSP for action in client_actions) and adapter.lsp_target:
            paths.append(adapter.lsp_target)
        guidance = _guidance_target(adapter)
        if guidance is not None:
            paths.append(guidance)
    return tuple(dict.fromkeys(paths))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""
    except UnicodeDecodeError as exc:
        raise ExecutionError(f"Configuration is not UTF-8: {path}") from exc


def _write_text(path: Path, text: str) -> None:
    atomic_write(path, text.encode("utf-8"))


def _install_languages(
    plan: InstallPlan,
    manifests: ManifestSet,
    runner: CommandRunner,
    which: Callable[[str], str | None],
) -> None:
    if not any(action.layer is Layer.LSP for action in plan.actions):
        return
    for language in plan.languages:
        definition = manifests.languages["languages"][language]
        server = definition["server"]
        if which(server):
            continue
        installer = tuple(definition["installer"])
        _run_required(runner, installer, f"{language} language-server installation", timeout=300)


def _configure_lsp(
    plan: InstallPlan,
    adapters: dict[ClientId, ClientAdapter],
    runner: CommandRunner,
) -> None:
    for client_id in plan.selected_clients:
        if not any(
            action.client is client_id and action.layer is Layer.LSP for action in plan.actions
        ):
            continue
        adapter = adapters[client_id]
        target = adapter.lsp_target
        if target is not None:
            rendered = adapter.render_lsp(_read_text(target), plan.languages)
            if rendered is not None:
                _write_text(target, rendered)
        for command in adapter.lsp_commands(plan.languages):
            _run_required(runner, command, f"Claude LSP plugin setup for {command[3]}", timeout=300)


def _configure_guidance(adapters: dict[ClientId, ClientAdapter]) -> None:
    content = (
        "Prefix supported shell commands with `rtk` to compact tool output before it enters "
        "the agent context. Use raw output when compression hides required detail."
    )
    for adapter in adapters.values():
        target = _guidance_target(adapter)
        if target is None:
            continue
        _write_text(target, set_owned_block(_read_text(target), "rtk-routing", content))


def _install_codex_jmunch(
    adapter: ClientAdapter,
    manifests: ManifestSet,
    runner: CommandRunner,
    uv_command: str,
) -> None:
    for component in ("jcodemunch", "jdocmunch", "jdatamunch"):
        tool = manifests.versions["tools"][component]
        prefix = (
            adapter.context.state_root
            / "tools"
            / "jmunch"
            / component
            / tool["version"]
        )
        environment = {
            "UV_TOOL_DIR": str(prefix / "tools"),
            "UV_TOOL_BIN_DIR": str(prefix / "bin"),
        }
        _run_required(
            runner,
            (uv_command, "tool", "install", f"{tool['package']}=={tool['version']}"),
            f"isolated {component} installation",
            environment=environment,
            timeout=300,
        )


def _configure_jmunch(
    plan: InstallPlan,
    manifests: ManifestSet,
    adapters: dict[ClientId, ClientAdapter],
    runner: CommandRunner,
    toolchain: Toolchain,
) -> None:
    clients = {
        action.client for action in plan.actions if action.layer is Layer.JMUNCH
    }
    if not clients:
        return
    if any(client is not ClientId.CODEX for client in clients) and toolchain.uvx_command is None:
        raise ExecutionError("uvx is required for jMunch MCP configuration")
    if ClientId.CODEX in clients and toolchain.uv_command is None:
        raise ExecutionError("uv is required for the isolated Codex jMunch installation")
    for client_id in clients:
        adapter = adapters[client_id]
        if client_id is ClientId.CODEX:
            assert toolchain.uv_command is not None
            _install_codex_jmunch(adapter, manifests, runner, toolchain.uv_command)
        target = adapter.mcp_target
        _write_text(target, adapter.render_mcp(_read_text(target)))


def execute_plan(
    plan: InstallPlan,
    manifests: ManifestSet,
    context: PathContext,
    *,
    runner: CommandRunner | None = None,
    which: Callable[[str], str | None] = shutil.which,
    rtk_installer: Callable[[ManifestSet, PathContext, Path], None] = install_verified_rtk,
) -> ExecutionReport:
    if plan.options.dry_run:
        raise ExecutionError("a dry-run plan cannot be executed")
    command_runner = runner or SubprocessRunner()
    toolchain = resolve_toolchain(context, which=which)
    adapters = {
        client: adapter_for(
            client,
            manifests,
            context,
            plan.options.project,
            toolchain.uvx_command or "uvx",
        )
        for client in plan.selected_clients
    }

    paths = _target_paths(plan, adapters, toolchain)
    operation: BackupOperation | None = None
    manager = BackupManager(context.state_root)
    if paths:
        operation = manager.begin(paths, plan.options.jmunch_use)
    try:
        materialize_bootstrap_uv(toolchain)
        if toolchain.rtk_install_required:
            rtk_installer(manifests, context, Path(toolchain.rtk_command))
        _rtk_preflight(plan, command_runner, toolchain.rtk_command)
        _configure_guidance(adapters)
        _install_languages(plan, manifests, command_runner, which)
        _configure_lsp(plan, adapters, command_runner)
        _configure_jmunch(plan, manifests, adapters, command_runner, toolchain)
    except ToolBootstrapError as exc:
        if operation is not None:
            manager.finalize(operation)
        raise ExecutionError(str(exc)) from exc
    except Exception:
        if operation is not None:
            manager.finalize(operation)
        raise
    if operation is not None:
        manager.finalize(operation)
    return ExecutionReport(operation.operation_id if operation else None, plan.results)
