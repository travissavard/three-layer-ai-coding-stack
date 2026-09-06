"""Bounded client and project-language detection."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .manifests import ManifestSet
from .models import ClientId, Detection
from .paths import PathContext, configured_path_templates

VersionProbe = Callable[[Path, tuple[str, ...]], str | None]
_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)")


def _probe_version(executable: Path, args: tuple[str, ...]) -> str | None:
    """Run only a bounded, non-agent version command and return its redacted output."""

    try:
        completed = subprocess.run(
            (str(executable), *args),
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return "\n".join(part for part in (completed.stdout, completed.stderr) if part)


def _parsed_version(output: str | None) -> str | None:
    if not output:
        return None
    match = _VERSION_PATTERN.search(output)
    if match is None:
        return None
    parts = match.group(1).split(".")
    return ".".join((*parts, *("0" for _ in range(3 - len(parts)))))


def detect_clients(
    manifests: ManifestSet,
    context: PathContext,
    *,
    which: Callable[[str], str | None] = shutil.which,
    version_probe: VersionProbe = _probe_version,
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
        probe_args = manifest.get("version_probe", ["--version"])
        version = None
        if executable is not None and isinstance(probe_args, list) and all(
            isinstance(item, str) for item in probe_args
        ):
            version = _parsed_version(version_probe(executable, tuple(probe_args)))
        detections[client_id] = Detection(
            client=client_id,
            detected=executable is not None or bool(paths),
            executable=executable,
            config_paths=paths,
            version=version,
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
