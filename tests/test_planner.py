from pathlib import Path

from three_layer_installer.cli import parse_args
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId, Detection, Layer, Status
from three_layer_installer.planner import build_plan

PROJECT_RTK_CLIENTS = {
    ClientId.KIMI: ("init", "--agent", "kimi"),
    ClientId.KILO: (),
    ClientId.ANTIGRAVITY: ("init", "--agent", "antigravity"),
}


def _detected(*clients: ClientId) -> dict[ClientId, Detection]:
    return {
        client: Detection(
            client=client,
            detected=client in clients,
            executable=Path(f"/usr/bin/{client.value}") if client in clients else None,
            version="999.0.0" if client in clients else None,
        )
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


def test_old_client_version_is_not_given_lsp_configuration(tmp_path: Path) -> None:
    detections = _detected(ClientId.QWEN)
    detections[ClientId.QWEN] = Detection(
        ClientId.QWEN,
        True,
        Path("/usr/bin/qwen"),
        version="0.8.2",
    )
    plan = build_plan(
        parse_args(
            [
                "--client",
                "qwen",
                "--project",
                str(tmp_path),
                "--languages",
                "python",
                "--jmunch-use",
                "skip",
            ]
        ),
        load_manifests(),
        detections,
    )

    lsp = next(item for item in plan.results if item.layer is Layer.LSP)
    assert lsp.status is Status.SKIPPED
    assert "requires Qwen Code 0.9.0 or newer" in lsp.message
    assert not any(action.layer is Layer.LSP for action in plan.actions)


def test_unknown_client_version_fails_closed_for_lsp(tmp_path: Path) -> None:
    detections = _detected(ClientId.QWEN)
    detections[ClientId.QWEN] = Detection(
        ClientId.QWEN,
        True,
        Path("/usr/bin/qwen"),
        version=None,
    )
    plan = build_plan(
        parse_args(
            [
                "--client",
                "qwen",
                "--project",
                str(tmp_path),
                "--languages",
                "python",
                "--jmunch-use",
                "skip",
            ]
        ),
        load_manifests(),
        detections,
    )

    lsp = next(item for item in plan.results if item.layer is Layer.LSP)
    assert lsp.status is Status.SKIPPED
    assert "version could not be verified" in lsp.message
    assert not any(action.layer is Layer.LSP for action in plan.actions)


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


def test_latest_plan_explicitly_removes_jmunch_package_pins() -> None:
    plan = build_plan(
        parse_args(
            [
                "--client",
                "claude",
                "--jmunch-use",
                "noncommercial",
                "--latest",
                "--dry-run",
            ]
        ),
        load_manifests(),
        _detected(ClientId.CLAUDE),
    )

    actions = [action for action in plan.actions if action.layer is Layer.JMUNCH]
    assert actions[0].argv == (
        "uvx",
        "--from",
        "jcodemunch-mcp",
        "jcodemunch-mcp",
    )


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


def test_claude_does_not_claim_unavailable_go_lsp_plugin() -> None:
    plan = build_plan(
        parse_args(
            [
                "--client",
                "claude",
                "--languages",
                "go",
                "--jmunch-use",
                "skip",
            ]
        ),
        load_manifests(),
        _detected(ClientId.CLAUDE),
    )

    lsp = next(result for result in plan.results if result.layer is Layer.LSP)
    assert lsp.status is Status.SKIPPED
    assert lsp.components == {"go": Status.SKIPPED}
    assert not any(action.layer is Layer.LSP for action in plan.actions)


def test_vscode_editor_lsp_does_not_install_standalone_servers() -> None:
    plan = build_plan(
        parse_args(
            [
                "--client",
                "vscode",
                "--languages",
                "python",
                "--jmunch-use",
                "skip",
            ]
        ),
        load_manifests(),
        _detected(ClientId.VSCODE),
    )

    lsp = next(result for result in plan.results if result.layer is Layer.LSP)
    assert lsp.status is Status.SKIPPED
    assert "editor" in lsp.message.lower()
    assert not any(action.layer is Layer.LSP for action in plan.actions)


def test_project_scoped_rtk_clients_require_an_explicit_project() -> None:
    for client in PROJECT_RTK_CLIENTS:
        plan = build_plan(
            parse_args(["--client", client.value, "--jmunch-use", "skip"]),
            load_manifests(),
            _detected(client),
        )

        rtk = next(result for result in plan.results if result.layer is Layer.RTK)
        assert rtk.status is Status.SKIPPED
        assert "--project" in rtk.message
        assert not any(action.layer is Layer.RTK for action in plan.actions)


def test_project_scoped_rtk_actions_use_project_as_working_directory(tmp_path: Path) -> None:
    for client, expected_argv in PROJECT_RTK_CLIENTS.items():
        plan = build_plan(
            parse_args(
                [
                    "--client",
                    client.value,
                    "--project",
                    str(tmp_path),
                    "--jmunch-use",
                    "skip",
                ]
            ),
            load_manifests(),
            _detected(client),
        )

        action = next(item for item in plan.actions if item.layer is Layer.RTK)
        assert action.argv == expected_argv
        assert action.path == tmp_path.resolve()
        assert "-g" not in action.argv
