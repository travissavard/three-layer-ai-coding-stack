from collections.abc import Mapping, Sequence
from pathlib import Path

from three_layer_installer.backup import BackupManager, atomic_write
from three_layer_installer.cli import run
from three_layer_installer.executor import CommandResult
from three_layer_installer.models import (
    ClientId,
    InstallPlan,
    JMunchUse,
    Layer,
    LayerResult,
    Status,
)
from three_layer_installer.paths import PathContext, PlatformKind


class SuccessfulRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        del argv, environment, cwd, timeout
        return CommandResult(0, "ok", "")


class FailingRtkRunner(SuccessfulRunner):
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        del environment, cwd, timeout
        if tuple(argv) == ("rtk", "init", "-g", "--auto-patch"):
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


def test_run_dry_run_prints_plan_without_persistent_writes(tmp_path: Path) -> None:
    output: list[str] = []

    exit_code = run(
        ["--client", "claude", "--dry-run"],
        output=output.append,
        context=_context(tmp_path),
        which=lambda name: "C:/tools/claude.exe" if name == "claude" else None,
    )

    assert exit_code == 0
    assert any("Three-Layer AI Coding Stack plan" in line for line in output)
    assert any("declaration required" in line for line in output)
    assert not (tmp_path / ".claude.json").exists()
    assert not (tmp_path / "Local" / "three-layer-ai-coding-stack").exists()


def test_run_licenses_prints_dual_use_notice_without_detection(tmp_path: Path) -> None:
    output: list[str] = []

    exit_code = run(["--licenses"], output=output.append, context=_context(tmp_path))

    assert exit_code == 0
    rendered = "\n".join(output)
    assert "jCodeMunch" in rendered
    assert "paid license" in rendered


def test_interactive_apply_combines_declaration_with_final_confirmation(tmp_path: Path) -> None:
    answers = iter(["noncommercial", "y"])
    prompts: list[str] = []
    output: list[str] = []

    def respond(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    exit_code = run(
        ["--client", "claude"],
        input_value=respond,
        output=output.append,
        context=_context(tmp_path),
        runner=SuccessfulRunner(),
        which=lambda name: f"C:/tools/{name}.exe",
        stack_verifier=lambda plan, *_args, **_kwargs: plan.results,
    )

    assert exit_code == 0
    assert "noncommercial" in prompts[1]
    assert (tmp_path / ".claude.json").is_file()
    assert "does not grant" in "\n".join(output)


def test_apply_runs_post_install_verification_and_returns_failure_status(
    tmp_path: Path,
) -> None:
    output: list[str] = []
    calls: list[str] = []

    def verify(
        plan: InstallPlan, _manifests: object, _context: object, **_kwargs: object
    ) -> tuple[LayerResult, ...]:
        calls.append("verify")
        return (
            LayerResult(
                ClientId.CLAUDE,
                Layer.RTK,
                Status.FAILED,
                "fixture verification failure",
            ),
            *(result for result in plan.results if result.layer is not Layer.RTK),
        )

    exit_code = run(
        ["--client", "claude", "--jmunch-use", "skip", "--yes"],
        output=output.append,
        context=_context(tmp_path),
        runner=SuccessfulRunner(),
        which=lambda name: f"C:/tools/{name}.exe",
        stack_verifier=verify,
    )

    assert exit_code == 4
    assert calls == ["verify"]
    rendered = "\n".join(output)
    assert "fixture verification failure" in rendered
    assert "Backup ID:" in rendered


def test_invalid_interactive_jmunch_declaration_fails_before_write(tmp_path: Path) -> None:
    exit_code = run(
        ["--client", "claude"],
        input_value=lambda _prompt: "maybe",
        output=lambda _message: None,
        context=_context(tmp_path),
        runner=SuccessfulRunner(),
        which=lambda name: f"C:/tools/{name}.exe",
    )

    assert exit_code == 2
    assert (tmp_path / ".claude.json").exists() is False


def test_run_restore_uses_hash_guarded_operation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    target = tmp_path / "client.json"
    target.write_text("before", encoding="utf-8")
    manager = BackupManager(context.state_root)
    operation = manager.begin((target,), JMunchUse.NONCOMMERCIAL)
    atomic_write(target, b"after")
    manager.finalize(operation)
    output: list[str] = []

    exit_code = run(
        ["--restore", operation.operation_id],
        output=output.append,
        context=context,
    )

    assert exit_code == 0
    assert target.read_text(encoding="utf-8") == "before"
    assert any(operation.operation_id in line for line in output)


def test_run_verify_calls_read_only_stack_verifier(tmp_path: Path) -> None:
    output: list[str] = []
    calls: list[str] = []

    def verify(
        plan: InstallPlan, _manifests: object, _context: object, **_kwargs: object
    ) -> tuple[LayerResult, ...]:
        calls.append("verify")
        return plan.results

    exit_code = run(
        [
            "--verify",
            "--client",
            "claude",
            "--jmunch-use",
            "skip",
        ],
        output=output.append,
        context=_context(tmp_path),
        runner=SuccessfulRunner(),
        which=lambda name: f"C:/tools/{name}.exe",
        stack_verifier=verify,
    )

    assert exit_code == 0
    assert calls == ["verify"]
    assert any("Three-Layer AI Coding Stack result" in line for line in output)


def test_failed_apply_reports_the_restorable_backup_id(tmp_path: Path) -> None:
    output: list[str] = []

    exit_code = run(
        ["--client", "claude", "--jmunch-use", "skip", "--yes"],
        output=output.append,
        context=_context(tmp_path),
        runner=FailingRtkRunner(),
        which=lambda name: f"C:/tools/{name}.exe",
    )

    assert exit_code == 4
    rendered = "\n".join(output)
    assert "Backup ID:" in rendered
    assert "--restore" in rendered
