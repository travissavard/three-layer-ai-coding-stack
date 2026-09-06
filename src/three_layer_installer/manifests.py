"""Loading and structural validation for the installer manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    """Raised when a required manifest cannot be loaded."""


@dataclass(frozen=True)
class ManifestSet:
    clients: dict[str, Any]
    languages: dict[str, Any]
    versions: dict[str, Any]
    licenses: dict[str, Any]
    bootstrap: dict[str, Any]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"Required manifest is missing: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest {path.name} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"Manifest {path.name} must contain a JSON object")
    return value


def load_manifests(root: Path | None = None) -> ManifestSet:
    config_root = (root or repository_root()) / "config"
    return ManifestSet(
        clients=_load_json(config_root / "clients.json"),
        languages=_load_json(config_root / "languages.json"),
        versions=_load_json(config_root / "versions.json"),
        licenses=_load_json(config_root / "licenses.json"),
        bootstrap=_load_json(config_root / "bootstrap.json"),
    )


def validate_manifests(manifests: ManifestSet) -> list[str]:
    """Return all cross-manifest errors instead of failing at the first one."""

    errors: list[str] = []
    layers = manifests.clients.get("layers", [])
    if [item.get("id") for item in layers if isinstance(item, dict)] != [1, 2, 3]:
        errors.append("clients.json must define layers 1, 2, and 3 in order")

    clients = manifests.clients.get("clients")
    tools = manifests.versions.get("tools")
    languages = manifests.languages.get("languages")
    records = manifests.licenses.get("components")
    if not isinstance(clients, dict) or not clients:
        errors.append("clients.json must define clients")
        clients = {}
    if not isinstance(tools, dict) or not tools:
        errors.append("versions.json must define tools")
        tools = {}
    if not isinstance(languages, dict) or not languages:
        errors.append("languages.json must define languages")
    if not isinstance(records, list):
        errors.append("licenses.json must define a components list")
        records = []

    license_ids = [
        item["id"]
        for item in records
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]
    duplicates = sorted({item for item in license_ids if license_ids.count(item) > 1})
    if duplicates:
        errors.append(f"duplicate license records: {', '.join(duplicates)}")

    covered = set(license_ids)
    missing_tools = sorted(set(tools) - covered)
    missing_clients = sorted(set(clients) - covered)
    if missing_tools:
        errors.append(f"tools missing license records: {', '.join(missing_tools)}")
    if missing_clients:
        errors.append(f"clients missing terms records: {', '.join(missing_clients)}")

    record_map = {
        item["id"]: item
        for item in records
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for component in ("jcodemunch", "jdocmunch", "jdatamunch"):
        record = record_map.get(component, {})
        if record.get("commercial_use") != "paid-license-required":
            errors.append(f"{component} must declare paid commercial licensing")
        if not str(record.get("license", "")).startswith("LicenseRef-"):
            errors.append(f"{component} must use a custom LicenseRef identifier")

    for item_id, record in record_map.items():
        for field_name in ("license", "license_url", "relationship"):
            if not record.get(field_name):
                errors.append(f"license record {item_id} is missing {field_name}")
    return errors
