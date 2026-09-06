from three_layer_installer.cli import parse_args
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId, Detection
from three_layer_installer.planner import build_plan
from three_layer_installer.reporting import render_license_notice, render_plan


def test_license_notice_names_all_components_and_commercial_requirement() -> None:
    notice = render_license_notice(load_manifests())

    assert "jCodeMunch" in notice
    assert "jDocMunch" in notice
    assert "jDataMunch" in notice
    assert notice.lower().count("paid license") >= 1
    assert "does not grant" in notice


def test_plan_is_layered_and_does_not_render_payload_values() -> None:
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
            ["--client", "claude", "--jmunch-use", "noncommercial", "--dry-run"]
        ),
        load_manifests(),
        detections,
    )
    plan_text = render_plan(plan, load_manifests())

    assert "Layer 1 — RTK" in plan_text
    assert "Layer 2 — Native LSP" in plan_text
    assert "Layer 3 — jMunch" in plan_text
    assert "JCODEMUNCH_SHARE_SAVINGS" not in plan_text
    assert "noncommercial" in plan_text


def test_plan_displays_pinned_versions_and_sources_before_install() -> None:
    detections = {
        client: Detection(
            client,
            client is ClientId.CLAUDE,
            None,
            version="999.0.0" if client is ClientId.CLAUDE else None,
        )
        for client in ClientId
    }
    manifests = load_manifests()
    plan = build_plan(
        parse_args(
            [
                "--client",
                "claude",
                "--languages",
                "python",
                "--jmunch-use",
                "noncommercial",
                "--dry-run",
            ]
        ),
        manifests,
        detections,
    )

    rendered = render_plan(plan, manifests)

    assert "Planned component versions and sources" in rendered
    assert "RTK 0.48.0 — https://github.com/rtk-ai/rtk/releases/tag/v0.48.0" in rendered
    assert (
        "Pyright 1.1.413 — https://www.npmjs.com/package/pyright/v/1.1.413"
        in rendered
    )
    assert (
        "jCodeMunch 1.108.317 — "
        "https://pypi.org/project/jcodemunch-mcp/1.108.317/" in rendered
    )
