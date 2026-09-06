import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from three_layer_installer.cli import parse_args
from three_layer_installer.executor import (
    CommandResult,
    ExecutionError,
    execute_plan,
)
from three_layer_installer.manifests import ManifestSet, load_manifests
from three_layer_installer.models import ClientId, Detection, InstallPlan
from three_layer_installer.paths import PathContext, PlatformKind
from three_layer_installer.planner import build_plan


class RecordingRunner:
    def __init__(
        self,
        failing_prefix: tuple[str, ...] | None = None,
        on_call: Callable[
            [tuple[str, ...], Mapping[str, str] | None, Path | None], None
        ]
        | None = None,
    ) -> None:
        self.calls: list[
            tuple[tuple[str, ...], Mapping[str, str] | None, Path | None]
        ] = []
        self.failing_prefix = failing_prefix
        self.on_call = on_call

    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        del timeout
        call = tuple(argv)
        self.calls.append((call, environment, cwd))
        if self.on_call:
            self.on_call(call, environment, cwd)
        if self.failing_prefix and call[: len(self.failing_prefix)] == self.failing_prefix:
            return CommandResult(1, "", "fixture failure")
        return CommandResult(0, "ok", "")


class InterruptingRunner(RecordingRunner):
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        if tuple(argv)[:3] == ("rtk", "init", "--dry-run"):
            raise KeyboardInterrupt
        return super().run(
            argv,
            environment=environment,
            cwd=cwd,
            timeout=timeout,
        )


def _context(tmp_path: Path) -> PathContext:
    return PathContext(
        PlatformKind.WINDOWS,
        tmp_path,
        {
            "APPDATA": str(tmp_path / "Roaming"),
            "LOCALAPPDATA": str(tmp_path / "Local"),
        },
    )


def _plan(args: list[str], *detected: ClientId) -> InstallPlan:
    detections = {
        client: Detection(
            client,
            client in detected,
            Path(f"C:/tools/{client.value}.exe") if client in detected else None,
            version="999.0.0" if client in detected else None,
        )
        for client in ClientId
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
    commands = [call for call, _environment, _cwd in runner.calls]
    assert ("rtk", "gain") in commands
    assert ("rtk", "init", "--dry-run", "-g", "--auto-patch") in commands
    assert ("rtk", "init", "-g", "--auto-patch") in commands


def test_fresh_claude_config_directory_exists_before_native_rtk_write(tmp_path: Path) -> None:
    context = _context(tmp_path)
    target = tmp_path / ".claude" / "RTK.md"

    def native_write(
        call: tuple[str, ...], _environment: Mapping[str, str] | None, _cwd: Path | None,
    ) -> None:
        if call == ("rtk", "init", "-g", "--auto-patch"):
            # RTK 0.48.0's atomic writer requires an already-existing parent directory.
            target.write_text("rtk fixture\n", encoding="utf-8")

    report = execute_plan(
        _plan(["--client", "claude", "--jmunch-use", "skip"], ClientId.CLAUDE),
        load_manifests(), context, runner=RecordingRunner(on_call=native_write),
        which=lambda name: f"C:/tools/{name}.exe",
    )
    assert target.read_text(encoding="utf-8") == "rtk fixture\n"
    assert report.operation_id is not None
    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    assert not target.exists()


def test_codex_installs_jmunch_into_isolated_uv_tool_directories(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text("", encoding="utf-8")
    def materialize_tool(
        call: tuple[str, ...], environment: Mapping[str, str] | None, _cwd: Path | None
    ) -> None:
        if call[:3] != ("uv", "tool", "install") or environment is None:
            return
        component = call[3].split("==", 1)[0].removesuffix("-mcp")
        executable = Path(environment["UV_TOOL_BIN_DIR"]) / f"{component}-mcp.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"tool")

    runner = RecordingRunner(on_call=materialize_tool)
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

    installs = [
        (call, env)
        for call, env, _cwd in runner.calls
        if call[:3] == ("uv", "tool", "install")
    ]
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


def test_undetected_explicit_client_provisions_nothing(tmp_path: Path) -> None:
    runner = RecordingRunner()
    plan = _plan(["--client", "qwen", "--jmunch-use", "skip"])

    def unexpected_rtk_install(
        _manifests: ManifestSet, _context: PathContext, _destination: Path
    ) -> None:
        pytest.fail("an undetected client must not install RTK")

    report = execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda _name: None,
        rtk_installer=unexpected_rtk_install,
    )

    assert runner.calls == []
    assert report.operation_id is None
    assert (tmp_path / ".qwen" / "QWEN.md").exists() is False
    assert (_context(tmp_path).state_root / "bin").exists() is False


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


def test_keyboard_interrupt_seals_a_restorable_operation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    plan = _plan(
        ["--client", "claude", "--jmunch-use", "skip"],
        ClientId.CLAUDE,
    )

    with pytest.raises(ExecutionError, match="interrupted") as error:
        execute_plan(
            plan,
            load_manifests(),
            context,
            runner=InterruptingRunner(),
            which=lambda name: f"C:/tools/{name}.exe",
        )

    assert error.value.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(error.value.operation_id)


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

    def install_rtk(
        _manifests: ManifestSet, _context: PathContext, destination: Path
    ) -> None:
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
    assert (str(installed[0]), "gain") in [call for call, _env, _cwd in runner.calls]
    assert report.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    assert installed[0].exists() is False


def test_unsupported_claude_language_does_not_install_a_server(tmp_path: Path) -> None:
    runner = RecordingRunner()
    plan = _plan(
        [
            "--client",
            "claude",
            "--languages",
            "go",
            "--jmunch-use",
            "skip",
        ],
        ClientId.CLAUDE,
    )

    execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )

    assert not any(call[:2] == ("go", "install") for call, _env, _cwd in runner.calls)


def test_missing_language_runtime_fails_before_install_command(tmp_path: Path) -> None:
    runner = RecordingRunner()
    plan = _plan(
        [
            "--client",
            "copilot",
            "--languages",
            "python",
            "--jmunch-use",
            "skip",
        ],
        ClientId.COPILOT,
    )

    with pytest.raises(ExecutionError, match="requires npm") as error:
        execute_plan(
            plan,
            load_manifests(),
            _context(tmp_path),
            runner=runner,
            which=lambda name: (
                f"C:/tools/{name}.exe" if name in {"rtk", "copilot"} else None
            ),
        )

    assert not any(call[:2] == ("npm", "install") for call, _env, _cwd in runner.calls)
    assert error.value.operation_id is not None


def test_latest_installs_unpinned_language_server_and_verified_latest_rtk(
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()
    plan = _plan(
        [
            "--client",
            "copilot",
            "--languages",
            "python",
            "--jmunch-use",
            "skip",
            "--latest",
        ],
        ClientId.COPILOT,
    )
    latest_installs: list[Path] = []

    def install_latest(
        _manifests: ManifestSet, _context: PathContext, destination: Path
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"latest-rtk")
        latest_installs.append(destination)

    execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda name: (
            f"C:/tools/{name}.exe" if name in {"copilot", "npm"} else None
        ),
        latest_rtk_installer=install_latest,
    )

    calls = [call for call, _environment, _cwd in runner.calls]
    assert latest_installs == [_context(tmp_path).state_root / "bin" / "rtk.exe"]
    assert ("npm", "install", "--global", "pyright") in calls
    assert not any("pyright@" in argument for call in calls for argument in call)


def test_latest_codex_upgrade_is_backed_up_and_restorable(tmp_path: Path) -> None:
    context = _context(tmp_path)
    tool_root = context.state_root / "tools" / "jmunch"
    for component in ("jcodemunch", "jdocmunch", "jdatamunch"):
        executable = tool_root / component / "latest" / "bin" / f"{component}-mcp.exe"
        executable.parent.mkdir(parents=True)
        executable.write_text("before", encoding="utf-8")

    def upgrade_tool(
        call: tuple[str, ...], _environment: Mapping[str, str] | None, _cwd: Path | None
    ) -> None:
        if call[:4] != ("uv", "tool", "install", "--upgrade"):
            return
        component = call[4].removesuffix("-mcp")
        executable = tool_root / component / "latest" / "bin" / f"{component}-mcp.exe"
        executable.write_text("upgraded", encoding="utf-8")

    runner = RecordingRunner(on_call=upgrade_tool)
    plan = _plan(
        [
            "--client",
            "codex",
            "--jmunch-use",
            "commercial-licensed",
            "--latest",
        ],
        ClientId.CODEX,
    )

    def install_latest(
        _manifests: ManifestSet, _context: PathContext, destination: Path
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"rtk")

    report = execute_plan(
        plan,
        load_manifests(),
        context,
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe" if name in {"uv", "uvx"} else None,
        latest_rtk_installer=install_latest,
    )

    assert report.operation_id is not None
    assert all(
        (tool_root / component / "latest" / "bin" / f"{component}-mcp.exe").read_text(
            encoding="utf-8"
        )
        == "upgraded"
        for component in ("jcodemunch", "jdocmunch", "jdatamunch")
    )

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    assert all(
        (tool_root / component / "latest" / "bin" / f"{component}-mcp.exe").read_text(
            encoding="utf-8"
        )
        == "before"
        for component in ("jcodemunch", "jdocmunch", "jdatamunch")
    )


def test_project_rtk_runs_in_project_with_telemetry_disabled_and_restores(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    agents_md = project / "AGENTS.md"
    agents_md.write_text("user instructions\n", encoding="utf-8")

    def mutate_rtk_config(
        call: tuple[str, ...], _environment: Mapping[str, str] | None, cwd: Path | None
    ) -> None:
        if call == ("rtk", "init", "--agent", "kimi"):
            assert cwd == project.resolve()
            agents_md.write_text("rtk changed this\n", encoding="utf-8")

    runner = RecordingRunner(on_call=mutate_rtk_config)
    plan = _plan(
        [
            "--client",
            "kimi",
            "--project",
            str(project),
            "--jmunch-use",
            "skip",
        ],
        ClientId.KIMI,
    )

    report = execute_plan(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )

    init_calls = [
        (call, environment, cwd)
        for call, environment, cwd in runner.calls
        if call[:2] == ("rtk", "init")
    ]
    assert init_calls == [
        (
            ("rtk", "init", "--dry-run", "--agent", "kimi"),
            {"RTK_TELEMETRY_DISABLED": "1"},
            project.resolve(),
        ),
        (
            ("rtk", "init", "--agent", "kimi"),
            {"RTK_TELEMETRY_DISABLED": "1"},
            project.resolve(),
        ),
    ]
    assert report.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(_context(tmp_path).state_root).restore(report.operation_id)
    assert agents_md.read_text(encoding="utf-8") == "user instructions\n"


def test_restore_covers_all_claude_files_that_native_rtk_can_change(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    existing = {
        claude_dir / "settings.json": b'{"userSetting":true}\n',
        hooks_dir / "rtk-rewrite.sh": b"legacy hook\n",
        hooks_dir / ".rtk-hook.sha256": b"legacy hash\n",
    }
    for path, content in existing.items():
        path.write_bytes(content)

    created = (
        claude_dir / "RTK.md",
        claude_dir / "CLAUDE.md",
        claude_dir / "settings.json.bak",
        tmp_path / "Roaming" / "rtk" / "filters.toml",
    )

    def mutate_rtk_config(
        call: tuple[str, ...],
        _environment: Mapping[str, str] | None,
        _cwd: Path | None,
    ) -> None:
        if call != ("rtk", "init", "-g", "--auto-patch"):
            return
        (claude_dir / "settings.json").write_text('{"hooks":{}}\n', encoding="utf-8")
        (hooks_dir / "rtk-rewrite.sh").unlink()
        (hooks_dir / ".rtk-hook.sha256").unlink()
        for path in created:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("created by rtk\n", encoding="utf-8")

    runner = RecordingRunner(on_call=mutate_rtk_config)
    plan = _plan(
        ["--client", "claude", "--jmunch-use", "skip"],
        ClientId.CLAUDE,
    )
    context = _context(tmp_path)

    report = execute_plan(
        plan,
        load_manifests(),
        context,
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )
    assert report.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    for path, content in existing.items():
        assert path.read_bytes() == content
    assert not any(path.exists() for path in created)


def test_restore_removes_new_isolated_codex_jmunch_tool_directories(tmp_path: Path) -> None:
    context = _context(tmp_path)

    def materialize_tool(
        call: tuple[str, ...], environment: Mapping[str, str] | None, _cwd: Path | None
    ) -> None:
        if call[:3] != ("uv", "tool", "install") or environment is None:
            return
        component = call[3].split("==", 1)[0].removesuffix("-mcp")
        executable = Path(environment["UV_TOOL_BIN_DIR"]) / f"{component}-mcp.exe"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"tool")

    runner = RecordingRunner(on_call=materialize_tool)
    plan = _plan(
        ["--client", "codex", "--jmunch-use", "commercial-licensed"],
        ClientId.CODEX,
    )

    report = execute_plan(
        plan,
        load_manifests(),
        context,
        runner=runner,
        which=lambda name: f"C:/tools/{name}.exe",
    )

    jmunch_root = context.state_root / "tools" / "jmunch"
    assert {path.name for path in jmunch_root.iterdir()} == {
        "jcodemunch",
        "jdocmunch",
        "jdatamunch",
    }
    assert report.operation_id is not None

    from three_layer_installer.backup import BackupManager

    BackupManager(context.state_root).restore(report.operation_id)
    assert not any(jmunch_root.glob("*"))
