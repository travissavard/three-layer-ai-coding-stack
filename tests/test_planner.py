from pathlib import Path

from three_layer_installer.cli import parse_args
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId, Detection, Layer, Status
from three_layer_installer.planner import build_plan


def _detected(*clients: ClientId) -> dict[ClientId, Detection]:
    return {
        client: Detection(client=client, detected=client in clients, executable=None)
        for client in ClientId
    }


def test_default_plan_selects_only_detected_clients() -> None:
    plan = build_plan(
        parse_args(["--dry-run"]),
        load_manifests(),
        _detected(ClientId.CLAUDE, ClientId.CODEX),
    )

    assert plan.selected_clients == (ClientId.CLAUDE, ClientId.CODEX)


def test_unsupported_client_reports_lsp_unavailable_from_client() -> None:
    plan = build_plan(
        parse_args(["--client", "codex", "--dry-run"]),
        load_manifests(),
        _detected(ClientId.CODEX),
    )

    result = next(item for item in plan.results if item.layer is Layer.LSP)
    assert result.status is Status.UNAVAILABLE_FROM_CLIENT
    assert "AI client" in result.message


def test_qwen_without_project_does_not_claim_lsp_active() -> None:
    plan = build_plan(
        parse_args(["--client", "qwen", "--languages", "python", "--dry-run"]),
        load_manifests(),
        _detected(ClientId.QWEN),
    )

    result = next(item for item in plan.results if item.layer is Layer.LSP)
    assert result.status is Status.SKIPPED
    assert "--project" in result.message


def test_jmunch_is_one_layer_with_three_component_actions() -> None:
    plan = build_plan(
        parse_args(
            [
                "--client",
                "claude",
                "--jmunch-use",
                "noncommercial",
                "--dry-run",
            ]
        ),
        load_manifests(),
        _detected(ClientId.CLAUDE),
    )

    jmunch_actions = [action for action in plan.actions if action.layer is Layer.JMUNCH]
    assert {action.component for action in jmunch_actions} == {
        "jcodemunch",
        "jdocmunch",
        "jdatamunch",
    }
    assert sum(result.layer is Layer.JMUNCH for result in plan.results) == 1


def test_project_auto_languages_are_included_in_plan(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
    plan = build_plan(
        parse_args(
            [
                "--client",
                "claude",
                "--project",
                str(tmp_path),
                "--jmunch-use",
                "skip",
                "--dry-run",
            ]
        ),
        load_manifests(),
        _detected(ClientId.CLAUDE),
    )

    assert plan.languages == ("python",)
