import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from three_layer_installer.adapters import adapter_for
from three_layer_installer.cli import parse_args
from three_layer_installer.executor import CommandResult
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId, Detection, InstallPlan, Layer, Status
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
        cwd: Path | None = None,
        timeout: float = 60,
    ) -> CommandResult:
        del environment, cwd, timeout
        return CommandResult(0 if tuple(argv) == ("rtk", "gain") else 1, "", "")


def _context(tmp_path: Path) -> PathContext:
    claude = tmp_path / ".claude"
    (claude / "hooks").mkdir(parents=True, exist_ok=True)
    for name in ("RTK.md", "CLAUDE.md", "hooks/rtk-rewrite.sh"):
        (claude / name).write_text("rtk", encoding="utf-8")
    (claude / "settings.json").write_text(json.dumps({
        "hooks": "rtk",
        "enabledPlugins": {
            "pyright-lsp@claude-plugins-official": True,
            "typescript-lsp@claude-plugins-official": True,
        },
    }), encoding="utf-8")
    qwen = tmp_path / ".qwen"
    qwen.mkdir(exist_ok=True)
    (qwen / "QWEN.md").write_text("rtk", encoding="utf-8")
    return PathContext(
        PlatformKind.WINDOWS,
        tmp_path,
        {
            "APPDATA": str(tmp_path / "Roaming"),
            "LOCALAPPDATA": str(tmp_path / "Local"),
        },
    )


def _plan(tmp_path: Path) -> InstallPlan:
    detections = {
        client: Detection(
            client,
            client is ClientId.CLAUDE,
            None,
            version="999.0.0" if client is ClientId.CLAUDE else None,
        )
        for client in ClientId
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

    def check_mcp(_argv: Sequence[str], product: str, **_kwargs: object) -> ProtocolCheck:
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
    assert (
        next(result for result in results if result.layer is Layer.RTK).status
        is Status.CONFIGURED
    )
    assert (
        next(result for result in results if result.layer is Layer.LSP).status
        is Status.CONFIGURED
    )


def test_verify_stack_reports_one_mcp_component_failure(tmp_path: Path) -> None:
    context = _context(tmp_path)
    adapter = adapter_for(ClientId.CLAUDE, load_manifests(), context)
    adapter.mcp_target.write_text(adapter.render_mcp("{}\n"), encoding="utf-8")

    def check_mcp(_argv: Sequence[str], product: str, **_kwargs: object) -> ProtocolCheck:
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


def test_verify_ignores_language_not_integrated_by_selected_client(tmp_path: Path) -> None:
    detections = {
        client: Detection(
            client,
            client is ClientId.CLAUDE,
            None,
            version="999.0.0" if client is ClientId.CLAUDE else None,
        )
        for client in ClientId
    }
    plan = build_plan(
        parse_args(
            [
                "--verify",
                "--client",
                "claude",
                "--languages",
                "typescript,go",
                "--jmunch-use",
                "skip",
            ]
        ),
        load_manifests(),
        detections,
    )
    calls: list[tuple[str, ...]] = []

    def verify_lsp(command: Sequence[str], **_kwargs: object) -> ProtocolCheck:
        calls.append(tuple(command))
        return ProtocolCheck(True, "ok")

    results = verify_stack(
        plan,
        load_manifests(),
        _context(tmp_path),
        runner=Runner(),
        which=lambda name: f"C:/tools/{name}.exe",
        lsp_verifier=verify_lsp,
    )

    lsp = next(result for result in results if result.layer is Layer.LSP)
    assert calls == [("typescript-language-server", "--stdio")]
    assert lsp.components == {"typescript": Status.ACTIVE}


def test_verified_guidance_rtk_remains_guidance_only(tmp_path: Path) -> None:
    detections = {
        client: Detection(
            client,
            client is ClientId.QWEN,
            None,
            version="999.0.0" if client is ClientId.QWEN else None,
        )
        for client in ClientId
    }
    plan = build_plan(
        parse_args(["--verify", "--client", "qwen", "--jmunch-use", "skip"]),
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

    rtk = next(result for result in results if result.layer is Layer.RTK)
    assert rtk.status is Status.GUIDANCE_ONLY


def test_empty_mcp_config_cannot_pass_by_starting_expected_servers(tmp_path: Path) -> None:
    context = _context(tmp_path)
    adapter = adapter_for(ClientId.CLAUDE, load_manifests(), context)
    adapter.mcp_target.write_text("{}", encoding="utf-8")
    calls: list[str] = []

    def check(_argv: Sequence[str], product: str, **_kwargs: object) -> ProtocolCheck:
        calls.append(product)
        return ProtocolCheck(True, "ok")

    results = verify_stack(
        _plan(tmp_path), load_manifests(), context, runner=Runner(),
        which=lambda name: name, mcp_verifier=check,
        lsp_verifier=lambda *_args, **_kwargs: ProtocolCheck(True, "ok"),
    )
    assert calls == []
    jmunch = next(result for result in results if result.layer is Layer.JMUNCH)
    assert jmunch.status is Status.FAILED
