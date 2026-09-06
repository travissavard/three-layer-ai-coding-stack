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


def test_missing_manifest_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match=r"clients\.json"):
        load_manifests(tmp_path)
