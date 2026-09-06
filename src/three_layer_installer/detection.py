"""Bounded client and project-language detection."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from .manifests import ManifestSet
from .models import ClientId, Detection
from .paths import PathContext, configured_path_templates


def detect_clients(
    manifests: ManifestSet,
    context: PathContext,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[ClientId, Detection]:
    detections: dict[ClientId, Detection] = {}
    for client_id in ClientId:
        manifest = manifests.clients["clients"][client_id.value]
        executable: Path | None = None
        for name in manifest.get("executables", []):
            found = which(name)
            if found:
                executable = Path(found)
                break
        paths = tuple(
            path
            for template in configured_path_templates(manifest, context.platform)
            if (path := context.resolve(template)).exists()
        )
        detections[client_id] = Detection(
            client=client_id,
            detected=executable is not None or bool(paths),
            executable=executable,
            config_paths=paths,
        )
    return detections


def detect_project_languages(
    project: Path,
    manifests: ManifestSet,
    *,
    file_limit: int = 2_000,
) -> tuple[str, ...]:
    project = project.resolve()
    definitions = manifests.languages["languages"]
    detected: set[str] = set()
    for name, definition in definitions.items():
        if any((project / marker).exists() for marker in definition.get("markers", [])):
            detected.add(name)

    extensions = {
        extension: name
        for name, definition in definitions.items()
        if name not in detected
        for extension in definition.get("extensions", [])
    }
    visited = 0
    ignored = {".git", ".venv", "node_modules", "target", "dist", "build"}
    for _root, directories, files in os.walk(project):
        directories[:] = sorted(item for item in directories if item not in ignored)
        for filename in sorted(files):
            visited += 1
            language = extensions.get(Path(filename).suffix.lower())
            if language:
                detected.add(language)
            if visited >= file_limit:
                break
        if visited >= file_limit or len(detected) == len(definitions):
            break
    return tuple(name for name in definitions if name in detected)
