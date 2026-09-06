import json
from pathlib import Path

import pytest

from three_layer_installer.backup import BackupError, BackupManager, atomic_write
from three_layer_installer.models import JMunchUse


def test_operation_restores_existing_and_new_files_exactly(tmp_path: Path) -> None:
    state = tmp_path / "state"
    existing = tmp_path / "config.json"
    generated = tmp_path / "new.json"
    existing.write_bytes(b'{"before":true}\r\n')
    manager = BackupManager(state)
    operation = manager.begin((existing, generated), JMunchUse.NONCOMMERCIAL)

    atomic_write(existing, b'{"after":true}\n')
    atomic_write(generated, b'{"created":true}\n')
    manager.finalize(operation)
    manager.restore(operation.operation_id)

    assert existing.read_bytes() == b'{"before":true}\r\n'
    assert generated.exists() is False


def test_restore_preflight_refuses_every_change_when_one_file_diverged(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("before-first", encoding="utf-8")
    second.write_text("before-second", encoding="utf-8")
    manager = BackupManager(tmp_path / "state")
    operation = manager.begin((first, second), JMunchUse.COMMERCIAL_LICENSED)
    atomic_write(first, b"installed-first")
    atomic_write(second, b"installed-second")
    manager.finalize(operation)
    second.write_text("user-change", encoding="utf-8")

    with pytest.raises(BackupError, match="changed since installation"):
        manager.restore(operation.operation_id)

    assert first.read_text(encoding="utf-8") == "installed-first"
    assert second.read_text(encoding="utf-8") == "user-change"


def test_manifest_records_hashes_not_configuration_contents(tmp_path: Path) -> None:
    config = tmp_path / "client.json"
    config.write_text('{"token":"fixture-secret-value"}', encoding="utf-8")
    manager = BackupManager(tmp_path / "state")
    operation = manager.begin((config,), JMunchUse.NONCOMMERCIAL)
    atomic_write(config, b"{}")
    manager.finalize(operation)

    manifest_text = operation.manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert "fixture-secret-value" not in manifest_text
    assert manifest["jmunch_use"] == "noncommercial"
    assert len(manifest["files"][0]["before_sha256"]) == 64


def test_restore_removes_a_new_managed_directory_tree(tmp_path: Path) -> None:
    managed = tmp_path / "managed-tool"
    manager = BackupManager(tmp_path / "state")
    operation = manager.begin((managed,), JMunchUse.COMMERCIAL_LICENSED)
    (managed / "bin").mkdir(parents=True)
    (managed / "bin" / "tool").write_text("installed", encoding="utf-8")
    manager.finalize(operation)

    manager.restore(operation.operation_id)

    assert managed.exists() is False


def test_restore_refuses_a_changed_managed_directory_tree(tmp_path: Path) -> None:
    managed = tmp_path / "managed-tool"
    manager = BackupManager(tmp_path / "state")
    operation = manager.begin((managed,), JMunchUse.COMMERCIAL_LICENSED)
    managed.mkdir()
    executable = managed / "tool"
    executable.write_text("installed", encoding="utf-8")
    manager.finalize(operation)
    executable.write_text("changed later", encoding="utf-8")

    with pytest.raises(BackupError, match="changed since installation"):
        manager.restore(operation.operation_id)

    assert executable.read_text(encoding="utf-8") == "changed later"


def test_operation_restores_an_existing_managed_directory_tree(tmp_path: Path) -> None:
    state = tmp_path / "state"
    managed = state / "tools" / "managed-tool"
    (managed / "bin").mkdir(parents=True)
    executable = managed / "bin" / "tool"
    executable.write_text("before", encoding="utf-8")
    manager = BackupManager(state)
    operation = manager.begin((managed,), JMunchUse.COMMERCIAL_LICENSED)
    executable.write_text("upgraded", encoding="utf-8")
    (managed / "new-metadata").write_text("created", encoding="utf-8")
    manager.finalize(operation)

    manager.restore(operation.operation_id)

    assert executable.read_text(encoding="utf-8") == "before"
    assert (managed / "new-metadata").exists() is False


def test_corrupt_backup_refuses_restore_before_any_mutation(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.write_text("before", encoding="utf-8")
    second.write_text("before", encoding="utf-8")
    manager = BackupManager(tmp_path / "state")
    operation = manager.begin((first, second), None)
    first.write_text("installed", encoding="utf-8")
    second.write_text("installed", encoding="utf-8")
    manager.finalize(operation)
    (operation.manifest_path.parent / "files" / "0001.bin").write_text(
        "corrupt", encoding="utf-8"
    )
    with pytest.raises(BackupError, match="corrupt"):
        manager.restore(operation.operation_id)
    assert first.read_text(encoding="utf-8") == "installed"
    assert second.read_text(encoding="utf-8") == "installed"
