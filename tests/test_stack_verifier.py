from collections.abc import Mapping, Sequence
from pathlib import Path

from three_layer_installer.adapters import adapter_for
from three_layer_installer.cli import parse_args
from three_layer_installer.executor import CommandResult
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId, Detection, Layer, Status
from three_layer_installer.paths import PathContext, PlatformKind
from three_layer_installer.planner import build_plan
from three_layer_installer.stack_verifier import verify_stack
from three_layer_installer.verification import ProtocolCheck


class Runner:
    def run(
        self,
        argv: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        del environment, timeout
        return CommandResult(0 if tuple(argv) == ("rtk", "gain") else 1, "", "")


def _context(tmp_path: Path) -> PathContext:
    return PathContext(
        PlatformKind.WINDOWS,
        tmp_path,
        {
            "APPDATA": str(tmp_path / "Roaming"),
            "LOCALAPPDATA": str(tmp_path / "Local"),
        },
    )


def _plan(tmp_path: Path):
    detections = {
        client: Detection(client, client is ClientId.CLAUDE, None) for client in ClientId
    }
    return build_plan(
        parse_args(
            [
                "--verify",
                "--client",
                "claude",
                "--languages",
                "python",
                "--jmunch-use",
                "noncommercial",
            ]
        ),
        load_manifests(),
        detections,
    )


def test_verify_stack_aggregates_three_mcp_components_as_one_layer(tmp_path: Path) -> None:
    context = _context(tmp_path)
    adapter = adapter_for(ClientId.CLAUDE, load_manifests(), context)
    adapter.mcp_target.write_text(adapter.render_mcp("{}\n"), encoding="utf-8")
    checked_products: list[str] = []

    def check_mcp(_argv: Sequence[str], product: str) -> ProtocolCheck:
        checked_products.append(product)
        return ProtocolCheck(True, "ok")

    results = verify_stack(
        _plan(tmp_path),
        load_manifests(),
        context,
        runner=Runner(),
        which=lambda name: f"C:/tools/{name}.exe",
        mcp_verifier=check_mcp,
        lsp_verifier=lambda *_args, **_kwargs: ProtocolCheck(True, "ok"),
    )

    jmunch = next(result for result in results if result.layer is Layer.JMUNCH)
    assert jmunch.status is Status.ACTIVE
    assert set(jmunch.components) == {"jcodemunch", "jdocmunch", "jdatamunch"}
    assert checked_products == ["jcodemunch", "jdocmunch", "jdatamunch"]
    assert next(result for result in results if result.layer is Layer.RTK).status is Status.ACTIVE
    assert next(result for result in results if result.layer is Layer.LSP).status is Status.ACTIVE


def test_verify_stack_reports_one_mcp_component_failure(tmp_path: Path) -> None:
    context = _context(tmp_path)
    adapter = adapter_for(ClientId.CLAUDE, load_manifests(), context)
    adapter.mcp_target.write_text(adapter.render_mcp("{}\n"), encoding="utf-8")

    def check_mcp(_argv: Sequence[str], product: str) -> ProtocolCheck:
        return ProtocolCheck(product != "jdocmunch", "fixture result")

    results = verify_stack(
        _plan(tmp_path),
        load_manifests(),
        context,
        runner=Runner(),
        which=lambda name: f"C:/tools/{name}.exe",
        mcp_verifier=check_mcp,
        lsp_verifier=lambda *_args, **_kwargs: ProtocolCheck(True, "ok"),
    )

    jmunch = next(result for result in results if result.layer is Layer.JMUNCH)
    assert jmunch.status is Status.FAILED
    assert jmunch.components["jdocmunch"] is Status.FAILED


def test_verify_stack_preserves_unavailable_lsp_classification(tmp_path: Path) -> None:
    detections = {
        client: Detection(client, client is ClientId.CODEX, None) for client in ClientId
    }
    plan = build_plan(
        parse_args(
            [
                "--verify",
                "--client",
                "codex",
                "--languages",
                "python",
                "--jmunch-use",
                "skip",
            ]
        ),
        load_manifests(),
        detections,
    )

    results = verify_stack(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=Runner(),
        which=lambda name: f"C:/tools/{name}.exe",
    )

    lsp = next(result for result in results if result.layer is Layer.LSP)
    assert lsp.status is Status.UNAVAILABLE_FROM_CLIENT
