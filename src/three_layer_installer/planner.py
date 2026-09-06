"""Create a non-secret declarative change plan."""

from __future__ import annotations

from .detection import detect_project_languages
from .manifests import ManifestSet
from .models import (
    ClientId,
    Detection,
    InstallerOptions,
    InstallPlan,
    JMunchUse,
    Layer,
    LayerResult,
    PlannedAction,
    Status,
    VerificationScope,
)


def _selected_clients(
    options: InstallerOptions, detections: dict[ClientId, Detection]
) -> tuple[ClientId, ...]:
    if options.clients:
        return options.clients
    return tuple(client for client in ClientId if detections[client].detected)


def _selected_languages(options: InstallerOptions, manifests: ManifestSet) -> tuple[str, ...]:
    selection = options.language_selection
    if selection.mode == "explicit":
        return selection.names
    if selection.mode == "auto" and options.project:
        return detect_project_languages(options.project, manifests)
    return ()


def build_plan(
    options: InstallerOptions,
    manifests: ManifestSet,
    detections: dict[ClientId, Detection],
) -> InstallPlan:
    selected = _selected_clients(options, detections)
    languages = _selected_languages(options, manifests)
    actions: list[PlannedAction] = []
    results: list[LayerResult] = []
    requires_declaration = False

    for client_id in selected:
        detection = detections[client_id]
        definition = manifests.clients["clients"][client_id.value]
        display_name = definition["display_name"]
        if not detection.detected:
            for layer in Layer:
                results.append(
                    LayerResult(
                        client_id,
                        layer,
                        Status.SKIPPED,
                        f"{display_name} was not detected",
                    )
                )
            continue

        rtk = definition["rtk"]
        rtk_status = Status.GUIDANCE_ONLY if rtk["mode"] == "guidance" else Status.CONFIGURED
        actions.append(
            PlannedAction(
                kind=f"rtk-{rtk['mode']}",
                client=client_id,
                layer=Layer.RTK,
                description=f"Configure RTK for {display_name}",
                argv=tuple(rtk.get("args", ())),
            )
        )
        results.append(
            LayerResult(
                client_id,
                Layer.RTK,
                rtk_status,
                "RTK routing will be configured",
                verification_scope=VerificationScope.CONFIG_ONLY,
            )
        )

        lsp = definition["lsp"]
        classification = lsp["classification"]
        if classification == "unavailable":
            results.append(
                LayerResult(
                    client_id,
                    Layer.LSP,
                    Status.UNAVAILABLE_FROM_CLIENT,
                    "The AI client does not expose native agent-facing LSP tools",
                )
            )
        elif not languages:
            results.append(
                LayerResult(client_id, Layer.LSP, Status.SKIPPED, "No language pack selected")
            )
        elif lsp.get("scope") == "project" and options.project is None:
            results.append(
                LayerResult(
                    client_id,
                    Layer.LSP,
                    Status.SKIPPED,
                    "This client requires --project for LSP configuration",
                )
            )
        else:
            for language in languages:
                actions.append(
                    PlannedAction(
                        kind="configure-lsp",
                        client=client_id,
                        layer=Layer.LSP,
                        component=language,
                        description=f"Configure {language} LSP for {display_name}",
                    )
                )
            status = {
                "experimental": Status.EXPERIMENTAL,
                "editor": Status.CONFIGURED,
            }.get(classification, Status.CONFIGURED)
            results.append(
                LayerResult(
                    client_id,
                    Layer.LSP,
                    status,
                    "Native LSP configuration is planned",
                    verification_scope=VerificationScope.CONFIG_ONLY,
                )
            )

        if options.jmunch_use is JMunchUse.SKIP:
            results.append(
                LayerResult(
                    client_id,
                    Layer.JMUNCH,
                    Status.SKIPPED,
                    "jMunch was explicitly skipped",
                )
            )
        elif options.jmunch_use is None:
            requires_declaration = True
            results.append(
                LayerResult(
                    client_id,
                    Layer.JMUNCH,
                    Status.SKIPPED,
                    "An explicit jMunch license basis is required before apply",
                )
            )
        else:
            component_status: dict[str, Status] = {}
            for component in ("jcodemunch", "jdocmunch", "jdatamunch"):
                tool = manifests.versions["tools"][component]
                package_spec = f"{tool['package']}=={tool['version']}"
                actions.append(
                    PlannedAction(
                        kind="configure-jmunch",
                        client=client_id,
                        layer=Layer.JMUNCH,
                        component=component,
                        description=f"Configure {component} for {display_name}",
                        argv=("uvx", "--from", package_spec, tool["executable"]),
                    )
                )
                component_status[component] = Status.CONFIGURED
            results.append(
                LayerResult(
                    client_id,
                    Layer.JMUNCH,
                    Status.CONFIGURED,
                    "All three jMunch MCP components will be configured as one layer",
                    components=component_status,
                    verification_scope=VerificationScope.CONFIG_ONLY,
                )
            )

    return InstallPlan(
        options=options,
        selected_clients=selected,
        languages=languages,
        actions=tuple(actions),
        results=tuple(results),
        requires_jmunch_declaration=requires_declaration,
    )
