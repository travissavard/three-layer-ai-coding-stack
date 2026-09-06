"""Command-line interface for the three-layer installer."""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from .backup import BackupError, BackupManager
from .detection import detect_clients
from .executor import CommandRunner, ExecutionError, execute_plan
from .manifests import ManifestSet, load_manifests, validate_manifests
from .models import (
    ClientId,
    InstallerOptions,
    JMunchUse,
    LanguageSelection,
    LayerResult,
    OperationMode,
    Status,
)
from .paths import PathContext
from .planner import build_plan
from .reporting import (
    render_license_inventory,
    render_license_notice,
    render_plan,
    render_results,
)
from .stack_verifier import verify_stack

LANGUAGES = ("typescript", "python", "rust", "go")


def _language_selection(value: str | None, project: Path | None) -> LanguageSelection:
    if value is None:
        return LanguageSelection("auto" if project else "none")
    if value in {"auto", "none"}:
        return LanguageSelection(value)
    names = tuple(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))
    unknown = sorted(set(names) - set(LANGUAGES))
    if not names or unknown:
        message = "language list must contain: " + ", ".join(LANGUAGES)
        raise argparse.ArgumentTypeError(message)
    return LanguageSelection("explicit", names)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="three-layer-install",
        description="Install RTK, native LSP integrations, and the combined jMunch layer.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--client", action="append", choices=[item.value for item in ClientId])
    selection.add_argument("--all", action="store_true", dest="all_clients")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--restore", metavar="BACKUP_ID")
    mode.add_argument("--licenses", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", dest="assume_yes")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--languages")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--jmunch-use", choices=[item.value for item in JMunchUse])
    return parser


def parse_args(argv: Sequence[str] | None = None) -> InstallerOptions:
    parser = _parser()
    namespace = parser.parse_args(argv)
    if namespace.restore:
        operation = OperationMode.RESTORE
    elif namespace.licenses:
        operation = OperationMode.LICENSES
    elif namespace.verify:
        operation = OperationMode.VERIFY
    else:
        operation = OperationMode.INSTALL
    if operation is not OperationMode.INSTALL and namespace.dry_run:
        parser.error("--dry-run is only valid for installation planning")

    project = namespace.project.resolve() if namespace.project else None
    try:
        languages = _language_selection(namespace.languages, project)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    jmunch_use = JMunchUse(namespace.jmunch_use) if namespace.jmunch_use else None
    needs_unattended_basis = (
        namespace.assume_yes
        and operation in {OperationMode.INSTALL, OperationMode.VERIFY}
        and not namespace.dry_run
        and jmunch_use is None
    )
    if needs_unattended_basis:
        parser.error(
            "unattended jMunch use requires --jmunch-use "
            "noncommercial|commercial-licensed|skip"
        )

    return InstallerOptions(
        mode=operation,
        dry_run=namespace.dry_run,
        assume_yes=namespace.assume_yes,
        clients=tuple(ClientId(item) for item in namespace.client or ()),
        all_clients=namespace.all_clients,
        project=project,
        language_selection=languages,
        latest=namespace.latest,
        jmunch_use=jmunch_use,
        restore_id=namespace.restore,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    input_value: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
    context: PathContext | None = None,
    runner: CommandRunner | None = None,
    which: Callable[[str], str | None] = shutil.which,
    manifests: ManifestSet | None = None,
    stack_verifier: Callable[..., tuple[LayerResult, ...]] = verify_stack,
) -> int:
    options = parse_args(argv)
    loaded = manifests or load_manifests()
    errors = validate_manifests(loaded)
    if errors:
        output("Installer manifests are invalid:\n- " + "\n- ".join(errors))
        return 3
    active_context = context or PathContext.current()

    if options.mode is OperationMode.LICENSES:
        output(render_license_inventory(loaded))
        return 0
    if options.mode is OperationMode.RESTORE:
        if options.restore_id is None:
            output("A backup identifier is required.")
            return 2
        try:
            BackupManager(active_context.state_root).restore(options.restore_id)
        except BackupError as exc:
            output(f"Restore refused: {exc}")
            return 5
        output(f"Restored configuration operation {options.restore_id}.")
        return 0

    detections = detect_clients(loaded, active_context, which=which)
    plan = build_plan(options, loaded, detections)
    if not plan.selected_clients:
        output("No supported AI clients were detected. Use --client to inspect one explicitly.")
        return 3

    notice_printed = False
    if plan.requires_jmunch_declaration:
        output(render_license_notice(loaded))
        notice_printed = True
        if options.dry_run:
            output(render_plan(plan, loaded))
            return 0
        answer = input_value(
            "Declare jMunch use [noncommercial/commercial-licensed/skip]: "
        ).strip()
        try:
            basis = JMunchUse(answer)
        except ValueError:
            output("No valid jMunch use basis was declared; no changes were made.")
            return 2
        options = replace(options, jmunch_use=basis)
        plan = build_plan(options, loaded, detections)

    if options.jmunch_use is not JMunchUse.SKIP and not notice_printed:
        output(render_license_notice(loaded))
    output(render_plan(plan, loaded))

    if options.mode is OperationMode.VERIFY:
        results = stack_verifier(
            plan,
            loaded,
            active_context,
            runner=runner,
            which=which,
        )
        output(render_results(results, loaded))
        return 4 if any(result.status is Status.FAILED for result in results) else 0
    if options.dry_run:
        return 0
    if not options.assume_yes:
        basis_label = options.jmunch_use.value if options.jmunch_use else "not enabled"
        confirmation = input_value(
            f"Apply this plan, including jMunch under '{basis_label}'? [y/N]: "
        ).strip()
        if confirmation.lower() not in {"y", "yes"}:
            output("Installation cancelled; no changes were made.")
            return 0
    try:
        report = execute_plan(
            plan,
            loaded,
            active_context,
            runner=runner,
            which=which,
        )
    except ExecutionError as exc:
        output(f"Installation failed: {exc}")
        if exc.operation_id:
            output(
                f"Backup ID: {exc.operation_id} (restore with --restore {exc.operation_id})"
            )
        return 4
    output(render_results(report.results, loaded))
    if report.operation_id:
        output(f"Backup ID: {report.operation_id}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)
