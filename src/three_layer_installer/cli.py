"""Command-line interface for the three-layer installer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .models import (
    ClientId,
    InstallerOptions,
    JMunchUse,
    LanguageSelection,
    OperationMode,
)

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


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    return 0
