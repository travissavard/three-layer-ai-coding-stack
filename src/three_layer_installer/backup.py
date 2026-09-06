"""Atomic writes and hash-guarded configuration restore."""

from __future__ import annotations

import hashlib
import json
import os
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
    return _sha256(path.read_bytes()) if path.is_file() else None


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
        unique_paths = tuple(dict.fromkeys(path.resolve() for path in paths))
        for index, path in enumerate(unique_paths):
            existed = path.is_file()
            before = path.read_bytes() if existed else None
            backup_name = f"{index:04d}.bin" if existed else None
            if before is not None and backup_name is not None:
                atomic_write(backups / backup_name, before)
            records.append(
                {
                    "path": str(path),
                    "existed": existed,
                    "backup": backup_name,
                    "before_sha256": _sha256(before) if before is not None else None,
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

        for record in manifest["files"]:
            path = Path(record["path"])
            if _current_hash(path) != record.get("after_sha256"):
                raise BackupError(f"{path} changed since installation; restore made no changes")

        backup_root = manifest_path.parent / "files"
        for record in manifest["files"]:
            path = Path(record["path"])
            if record["existed"]:
                backup_name = record.get("backup")
                if not isinstance(backup_name, str):
                    raise BackupError(f"backup data is missing for {path}")
                atomic_write(path, (backup_root / backup_name).read_bytes())
            elif path.exists():
                path.unlink()

        manifest["status"] = "restored"
        manifest["restored_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + "\n").encode())
