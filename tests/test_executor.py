import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from three_layer_installer.cli import parse_args
from three_layer_installer.executor import (
    CommandResult,
    ExecutionError,
    execute_plan,
)
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId, Detection
from three_layer_installer.paths import PathContext, PlatformKind
from three_layer_installer.planner import build_plan


class RecordingRunner:
    def __init__(self, failing_prefix: tuple[str, ...] | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], Mapping[str, str] | None]] = []
        self.failing_prefix = failing_prefix

    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        del timeout
        call = tuple(argv)
        self.calls.append((call, environment))
        if self.failing_prefix and call[: len(self.failing_prefix)] == self.failing_prefix:
            return CommandResult(1, "", "fixture failure")
        return CommandResult(0, "ok", "")


def _context(tmp_path: Path) -> PathContext:
    return PathContext(
        PlatformKind.WINDOWS,
        tmp_path,
        {
            "APPDATA": str(tmp_path / "Roaming"),
            "LOCALAPPDATA": str(tmp_path / "Local"),
        },
    )


def _plan(args: list[str], *detected: ClientId):
    detections = {
        client: Detection(client, client in detected, None) for client in ClientId
    }
    return build_plan(parse_args(args), load_manifests(), detections)


def test_apply_configures_claude_and_records_restorable_operation(tmp_path: Path) -> None:
    claude_config = tmp_path / ".claude.json"
    claude_config.write_text('{"apiToken":"fixture-secret-value"}\n', encoding="utf-8")
    runner = RecordingRunner()
    plan = _plan(
        ["--client", "claude", "--jmunch-use", "noncommercial"],
        ClientId.CLAUDE,
    )

    report = execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )

    parsed = json.loads(claude_config.read_text(encoding="utf-8"))
    assert parsed["apiToken"] == "fixture-secret-value"
    assert set(parsed["mcpServers"]) == {"jcodemunch", "jdocmunch", "jdatamunch"}
    assert report.operation_id
    assert (tmp_path / "Local" / "three-layer-ai-coding-stack" / "operations").is_dir()
    commands = [call for call, _environment in runner.calls]
    assert ("rtk", "gain") in commands
    assert ("rtk", "init", "--dry-run", "-g", "--auto-patch") in commands
    assert ("rtk", "init", "-g", "--auto-patch") in commands


def test_codex_installs_jmunch_into_isolated_uv_tool_directories(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("", encoding="utf-8")
    runner = RecordingRunner()
    plan = _plan(
        ["--client", "codex", "--jmunch-use", "commercial-licensed"],
        ClientId.CODEX,
    )

    execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )

    installs = [(call, env) for call, env in runner.calls if call[:3] == ("uv", "tool", "install")]
    assert len(installs) == 3
    assert all(env and "UV_TOOL_DIR" in env and "UV_TOOL_BIN_DIR" in env for _call, env in installs)


def test_guidance_client_gets_owned_rtk_block(tmp_path: Path) -> None:
    runner = RecordingRunner()
    plan = _plan(
        ["--client", "qwen", "--jmunch-use", "skip"],
        ClientId.QWEN,
    )

    execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )

    guidance = (tmp_path / ".qwen" / "QWEN.md").read_text(encoding="utf-8")
    assert "three-layer:rtk-routing:start" in guidance
    assert "Prefix supported shell commands with `rtk`" in guidance


def test_failed_rtk_identity_check_does_not_write_client_config(tmp_path: Path) -> None:
    runner = RecordingRunner(("rtk", "gain"))
    plan = _plan(
        ["--client", "claude", "--jmunch-use", "noncommercial"],
        ClientId.CLAUDE,
    )

    with pytest.raises(ExecutionError, match="RTK identity check failed"):
        execute_plan(
            plan,
            load_manifests(),
            _context(tmp_path),
            runner=runner,
            which=lambda name: f"C:/tools/{name}.exe",
        )

    assert (tmp_path / ".claude.json").exists() is False


def test_apply_persists_bootstrap_uv_and_uses_managed_absolute_command(
    tmp_path: Path,
) -> None:
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "uv.exe").write_bytes(b"uv")
    (bootstrap / "uvx.exe").write_bytes(b"uvx")
    context = _context(tmp_path)
    context = PathContext(
        context.platform,
        context.home,
        {**context.environment, "THREE_LAYER_BOOTSTRAP_UV_DIR": str(bootstrap)},
    )
    runner = RecordingRunner()
    plan = _plan(
        ["--client", "claude", "--jmunch-use", "noncommercial"],
        ClientId.CLAUDE,
    )

    report = execute_plan(
        plan,
        load_manifests(),
        context,
        runner=runner,
        which=lambda name: "C:/tools/rtk.exe" if name == "rtk" else None,
    )

    managed_uvx = context.state_root / "bin" / "uvx.exe"
    config = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["jcodemunch"]["command"] == str(managed_uvx.resolve())
    assert managed_uvx.read_bytes() == b"uvx"
    assert report.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    assert managed_uvx.exists() is False
    assert (context.state_root / "bin" / "uv.exe").exists() is False


def test_apply_installs_missing_rtk_inside_restorable_transaction(tmp_path: Path) -> None:
    context = _context(tmp_path)
    runner = RecordingRunner()
    plan = _plan(
        ["--client", "qwen", "--jmunch-use", "skip"],
        ClientId.QWEN,
    )
    installed: list[Path] = []

    def install_rtk(_manifests, _context, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"rtk")
        installed.append(destination)

    report = execute_plan(
        plan,
        load_manifests(),
        context,
        runner=runner,
        which=lambda _name: None,
        rtk_installer=install_rtk,
    )

    assert installed == [context.state_root / "bin" / "rtk.exe"]
    assert (str(installed[0]), "gain") in [call for call, _env in runner.calls]
    assert report.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    assert installed[0].exists() is False
