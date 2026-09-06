from pathlib import Path

import pytest

from three_layer_installer.cli import parse_args
from three_layer_installer.models import ClientId, JMunchUse, OperationMode


def test_cli_defaults_to_detected_clients_and_no_languages_without_project() -> None:
    options = parse_args([])

    assert options.mode is OperationMode.INSTALL
    assert options.clients == ()
    assert options.all_clients is False
    assert options.language_selection.mode == "none"
    assert options.jmunch_use is None


def test_cli_project_defaults_languages_to_auto() -> None:
    options = parse_args(["--project", "example"])

    assert options.project == Path("example").resolve()
    assert options.language_selection.mode == "auto"


def test_cli_parses_repeatable_clients_and_language_list() -> None:
    options = parse_args(
        [
            "--client",
            "claude",
            "--client",
            "codex",
            "--languages",
            "typescript,python",
            "--jmunch-use",
            "commercial-licensed",
        ]
    )

    assert options.clients == (ClientId.CLAUDE, ClientId.CODEX)
    assert options.language_selection.names == ("typescript", "python")
    assert options.jmunch_use is JMunchUse.COMMERCIAL_LICENSED


def test_unattended_apply_requires_explicit_jmunch_basis() -> None:
    with pytest.raises(SystemExit) as error:
        parse_args(["--yes"])

    assert error.value.code == 2


def test_dry_run_does_not_require_jmunch_basis() -> None:
    assert parse_args(["--dry-run", "--yes"]).dry_run is True


def test_restore_and_license_modes_do_not_require_jmunch_basis() -> None:
    assert parse_args(["--restore", "operation-1"]).mode is OperationMode.RESTORE
    assert parse_args(["--licenses"]).mode is OperationMode.LICENSES


def test_client_and_all_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as error:
        parse_args(["--client", "claude", "--all", "--dry-run"])

    assert error.value.code == 2

