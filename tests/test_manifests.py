from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from three_layer_installer.manifests import (
    ManifestError,
    load_manifests,
    validate_manifests,
)

EXPECTED_CLIENTS = {
    "claude",
    "codex",
    "copilot",
    "gemini",
    "qwen",
    "kimi",
    "kilo",
    "kiro",
    "antigravity",
    "vscode",
}


def test_shipped_manifests_are_complete_and_valid() -> None:
    manifests = load_manifests()

    assert set(manifests.clients["clients"]) == EXPECTED_CLIENTS
    assert validate_manifests(manifests) == []


def test_tested_versions_are_pinned() -> None:
    tools = load_manifests().versions["tools"]

    assert tools["rtk"]["version"] == "0.48.0"
    assert tools["uv"]["version"] == "0.12.10"
    assert tools["jcodemunch"]["version"] == "1.108.317"
    assert tools["jdocmunch"]["version"] == "1.139.1"
    assert tools["jdatamunch"]["version"] == "1.31.13"


def test_uv_bootstrap_assets_have_published_sha256_digests() -> None:
    bootstrap = load_manifests().bootstrap["uv"]

    assert bootstrap["version"] == "0.12.10"
    assert set(bootstrap["assets"]) == {
        "windows-x86_64",
        "windows-arm64",
        "macos-x86_64",
        "macos-arm64",
        "linux-x86_64",
        "linux-arm64",
    }
    assert all(len(asset["sha256"]) == 64 for asset in bootstrap["assets"].values())


def test_jmunch_components_have_separate_commercial_license_records() -> None:
    records = {item["id"]: item for item in load_manifests().licenses["components"]}

    for component in ("jcodemunch", "jdocmunch", "jdatamunch"):
        assert records[component]["commercial_use"] == "paid-license-required"
        assert records[component]["license"].startswith("LicenseRef-")
        assert records[component]["relationship"] == "installed-from-upstream"


def test_indexes_are_backing_stores_not_layers() -> None:
    layers = load_manifests().clients["layers"]

    assert len(layers) == 3
    assert not any("index" in layer["name"].lower() for layer in layers)


def test_every_client_integration_has_dated_primary_sources() -> None:
    clients = load_manifests().clients["clients"]

    for client, definition in clients.items():
        assert definition["verified_on"] == "2026-09-06", client
        assert set(definition["sources"]) == {"rtk", "lsp", "mcp"}, client
        assert all(
            source.startswith("https://") for source in definition["sources"].values()
        ), client


def test_native_lsp_clients_have_documented_minimum_version_gates() -> None:
    clients = load_manifests().clients["clients"]
    expected = {
        "claude": "2.0.74",
        "copilot": "0.0.405",
        "qwen": "0.9.0",
        "kilo": "1.0.0",
        "kiro": "1.22.0",
    }

    for client, minimum in expected.items():
        assert clients[client]["version_probe"] == ["--version"]
        assert clients[client]["lsp"]["minimum_version"] == minimum
        assert clients[client]["lsp"]["version_source"].startswith("https://")


def test_manifest_validation_rejects_missing_lsp_version_gate() -> None:
    manifests = load_manifests()
    clients = deepcopy(manifests.clients)
    del clients["clients"]["claude"]["lsp"]["minimum_version"]

    errors = validate_manifests(replace(manifests, clients=clients))

    assert "claude native LSP is missing a minimum_version" in errors


def test_manifest_validation_rejects_unknown_language_version_component() -> None:
    manifests = load_manifests()
    languages = deepcopy(manifests.languages)
    languages["languages"]["python"]["version_components"] = ["not-a-tool"]

    errors = validate_manifests(replace(manifests, languages=languages))

    assert "python references unknown version component: not-a-tool" in errors


def test_jcodemunch_license_identifier_matches_published_package_metadata() -> None:
    manifests = load_manifests()
    records = {item["id"]: item for item in manifests.licenses["components"]}

    assert manifests.versions["tools"]["jcodemunch"]["license_id"] == (
        "LicenseRef-jCodeMunch-Dual-Use-1"
    )
    assert records["jcodemunch"]["license"] == "LicenseRef-jCodeMunch-Dual-Use-1"
    assert records["jcodemunch"]["license_version"] == "1.1"


def test_missing_manifest_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match=r"clients\.json"):
        load_manifests(tmp_path)
