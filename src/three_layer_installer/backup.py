"""Atomic writes and hash-guarded configuration restore."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import JMunchUse


class BackupError(RuntimeError):
    """An operation cannot be backed up or safely restored."""


@dataclass(frozen=True)
class BackupOperation:
    operation_id: str
    manifest_path: Path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _current_hash(path: Path) -> str | None:
    if path.is_symlink():
        return _sha256(b"link\0" + os.readlink(path).encode())
    if path.is_file():
        return _sha256(path.read_bytes())
    if not path.is_dir():
        return None

    digest = hashlib.sha256()
    digest.update(b"directory\0")
    for root, directories, files in os.walk(path, followlinks=False):
        directories.sort()
        files.sort()
        root_path = Path(root)
        for name in (*directories, *files):
            child = root_path / name
            relative = child.relative_to(path).as_posix().encode()
            if child.is_symlink():
                digest.update(b"link\0" + relative + b"\0" + os.readlink(child).encode())
            elif child.is_dir():
                digest.update(b"directory\0" + relative + b"\0")
            else:
                digest.update(b"file\0" + relative + b"\0" + child.read_bytes())
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = path.stat().st_mode & 0o777 if path.exists() else None
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, mode or existing_mode or 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class BackupManager:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root

    @property
    def operations_root(self) -> Path:
        return self.state_root / "operations"

    def begin(
        self,
        paths: tuple[Path, ...],
        jmunch_use: JMunchUse | None,
    ) -> BackupOperation:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        operation_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
        directory = self.operations_root / operation_id
        backups = directory / "files"
        backups.mkdir(parents=True, exist_ok=False)
        if os.name != "nt":
            os.chmod(directory, 0o700)
            os.chmod(backups, 0o700)

        records: list[dict[str, Any]] = []
        if any(path.is_symlink() for path in paths):
            raise BackupError("refusing to back up a symbolic-link target")
        unique_paths = tuple(dict.fromkeys(path.resolve() for path in paths))
        for index, path in enumerate(unique_paths):
            if path.is_symlink():
                raise BackupError(f"refusing to back up a symbolic-link target: {path}")
            if path.is_dir():
                try:
                    relative = path.relative_to(self.state_root.resolve())
                except ValueError as exc:
                    raise BackupError(
                        f"refusing to back up a directory outside installer state: {path}"
                    ) from exc
                if not relative.parts or relative.parts[0] == "operations":
                    raise BackupError(f"refusing to back up installer operation state: {path}")
                kind = "directory"
                existed = True
                backup_name = f"{index:04d}.dir"
                shutil.copytree(path, backups / backup_name, symlinks=True)
            elif path.is_file():
                kind = "file"
                existed = True
                backup_name = f"{index:04d}.bin"
                atomic_write(backups / backup_name, path.read_bytes())
            else:
                kind = "missing"
                existed = False
                backup_name = None
            records.append(
                {
                    "path": str(path),
                    "kind": kind,
                    "existed": existed,
                    "backup": backup_name,
                    "before_sha256": _current_hash(path),
                    "after_sha256": None,
                }
            )
        manifest = {
            "schema_version": 1,
            "operation_id": operation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "planned",
            "jmunch_use": jmunch_use.value if jmunch_use else None,
            "files": records,
        }
        manifest_path = directory / "manifest.json"
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())
        return BackupOperation(operation_id, manifest_path)

    def _read_manifest(self, operation_id: str) -> tuple[Path, dict[str, Any]]:
        if not operation_id or Path(operation_id).name != operation_id:
            raise BackupError("invalid backup identifier")
        manifest_path = self.operations_root / operation_id / "manifest.json"
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise BackupError(f"backup manifest is unavailable: {operation_id}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("files"), list):
            raise BackupError(f"backup manifest is malformed: {operation_id}")
        return manifest_path, value

    def finalize(self, operation: BackupOperation) -> None:
        manifest_path, manifest = self._read_manifest(operation.operation_id)
        for record in manifest["files"]:
            record["after_sha256"] = _current_hash(Path(record["path"]))
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())

    def restore(self, operation_id: str) -> None:
        manifest_path, manifest = self._read_manifest(operation_id)
        if manifest.get("status") != "completed":
            raise BackupError("backup operation was not completed")

        backup_root = manifest_path.parent / "files"
        for record in manifest["files"]:
            path = Path(record["path"])
            if _current_hash(path) != record.get("after_sha256"):
                raise BackupError(f"{path} changed since installation; restore made no changes")
            if record["existed"]:
                name = record.get("backup")
                if not isinstance(name, str) or Path(name).name != name:
                    raise BackupError("backup data path is invalid; restore made no changes")
                source = backup_root / name
                if source.is_symlink() or _current_hash(source) != record.get("before_sha256"):
                    raise BackupError("backup data is missing or corrupt; restore made no changes")

        for record in manifest["files"]:
            path = Path(record["path"])
            kind = record.get("kind", "file" if record["existed"] else "missing")
            if kind == "directory":
                backup_name = record.get("backup")
                if not isinstance(backup_name, str):
                    raise BackupError(f"backup data is missing for {path}")
                source = backup_root / backup_name
                if not source.is_dir() or path.is_symlink() or not path.is_dir():
                    raise BackupError(f"directory backup data is invalid for {path}")
                staging = path.parent / f".{path.name}.restore-{uuid.uuid4().hex}"
                displaced = path.parent / f".{path.name}.replaced-{uuid.uuid4().hex}"
                shutil.copytree(source, staging, symlinks=True)
                os.replace(path, displaced)
                try:
                    os.replace(staging, path)
                except OSError:
                    os.replace(displaced, path)
                    raise
                shutil.rmtree(displaced)
            elif record["existed"]:
                backup_name = record.get("backup")
                if not isinstance(backup_name, str):
                    raise BackupError(f"backup data is missing for {path}")
                atomic_write(path, (backup_root / backup_name).read_bytes())
            elif path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

        manifest["status"] = "restored"
        manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())
