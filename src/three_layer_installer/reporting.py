"""Redacted, user-facing plan and status rendering."""

from __future__ import annotations

from .manifests import ManifestSet
from .models import InstallPlan, Layer, LayerResult


def render_license_notice(manifests: ManifestSet) -> str:
    records = {item["id"]: item for item in manifests.licenses["components"]}
    versions = manifests.versions["tools"]
    names = {
        "jcodemunch": "jCodeMunch",
        "jdocmunch": "jDocMunch",
        "jdatamunch": "jDataMunch",
    }
    lines = [
        "jMunch license notice",
        "----------------------",
        "Layer 3 contains three separately licensed components:",
    ]
    for component, display_name in names.items():
        lines.append(
            f"- {display_name} {versions[component]['version']}: "
            f"{records[component]['license_url']}"
        )
    lines.extend(
        [
            "Each component is free only for qualifying non-commercial use; commercial use "
            "requires a paid license from its publisher.",
            "Your declaration does not grant a license and this installer does not "
            "provide legal advice.",
        ]
    )
    return "\n".join(lines)


def render_license_inventory(manifests: ManifestSet) -> str:
    lines = [render_license_notice(manifests), "", "Complete component inventory"]
    for record in manifests.licenses["components"]:
        lines.append(
            f"- {record['id']}: {record['license']} ({record['relationship']}) — "
            f"{record['license_url']}"
        )
    lines.append(
        "AI-client subscriptions, API credits, and commercial entitlements remain separate "
        "from this installer."
    )
    return "\n".join(lines)


def _render_result(result: LayerResult, manifests: ManifestSet) -> str:
    display_name = manifests.clients["clients"][result.client.value]["display_name"]
    return f"  {display_name}: {result.status.value} — {result.message}"


def render_plan(plan: InstallPlan, manifests: ManifestSet) -> str:
    basis = plan.options.jmunch_use.value if plan.options.jmunch_use else "declaration required"
    lines = ["Three-Layer AI Coding Stack plan", f"jMunch use basis: {basis}"]
    for layer in Layer:
        lines.append("")
        lines.append(f"Layer {layer.value} — {layer.label}")
        layer_results = [result for result in plan.results if result.layer is layer]
        if not layer_results:
            lines.append("  No detected client selected")
        else:
            lines.extend(_render_result(result, manifests) for result in layer_results)
    lines.extend(["", f"Planned actions: {len(plan.actions)}"])
    return "\n".join(lines)


def render_results(results: tuple[LayerResult, ...], manifests: ManifestSet) -> str:
    lines = ["Three-Layer AI Coding Stack result"]
    for layer in Layer:
        lines.append("")
        lines.append(f"Layer {layer.value} — {layer.label}")
        lines.extend(
            _render_result(result, manifests) for result in results if result.layer is layer
        )
    return "\n".join(lines)
