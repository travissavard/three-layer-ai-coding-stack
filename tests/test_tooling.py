import hashlib
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from three_layer_installer.manifests import load_manifests
from three_layer_installer.paths import PathContext, PlatformKind
from three_layer_installer.tooling import (
    ToolBootstrapError,
    install_verified_rtk,
    materialize_bootstrap_uv,
    resolve_toolchain,
)


def _windows_context(tmp_path: Path, **environment: str) -> PathContext:
    return PathContext(
        PlatformKind.WINDOWS,
        tmp_path,
        {"LOCALAPPDATA": str(tmp_path / "Local"), **environment},
    )


def test_system_tools_are_reused_without_managed_targets(tmp_path: Path) -> None:
    toolchain = resolve_toolchain(
        _windows_context(tmp_path),
        which=lambda name: f"C:/tools/{name}.exe",
    )

    assert toolchain.rtk_command == "rtk"
    assert toolchain.uv_command == "uv"
    assert toolchain.uvx_command == "uvx"
    assert toolchain.managed_targets == ()
    assert toolchain.rtk_install_required is False


def test_verified_launcher_uv_is_copied_to_managed_bin(tmp_path: Path) -> None:
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "uv.exe").write_bytes(b"uv-fixture")
    (bootstrap / "uvx.exe").write_bytes(b"uvx-fixture")
    context = _windows_context(tmp_path, THREE_LAYER_BOOTSTRAP_UV_DIR=str(bootstrap))

    toolchain = resolve_toolchain(context, which=lambda _name: None)
    materialize_bootstrap_uv(toolchain)

    assert Path(toolchain.uv_command or "").read_bytes() == b"uv-fixture"
    assert Path(toolchain.uvx_command or "").read_bytes() == b"uvx-fixture"
    assert set(toolchain.managed_targets) >= {
        context.state_root / "bin" / "uv.exe",
        context.state_root / "bin" / "uvx.exe",
    }


def test_rtk_download_is_digest_checked_and_extracts_only_binary(tmp_path: Path) -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("release/rtk.exe", b"rtk-fixture")
        archive.writestr("release/README.txt", b"not installed")
    archive_bytes = archive_buffer.getvalue()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    manifests = load_manifests()
    bootstrap = dict(manifests.bootstrap)
    bootstrap["rtk"] = {
        "version": "fixture",
        "base_url": "https://github.com/rtk-ai/rtk/releases/download/vfixture/",
        "assets": {
            "windows-x86_64": {
                "name": "rtk-fixture.zip",
                "sha256": digest,
            }
        },
    }
    manifests = replace(manifests, bootstrap=bootstrap)
    destination = tmp_path / "managed" / "rtk.exe"

    def fetch(url: str, target: Path) -> None:
        assert url.endswith("/rtk-fixture.zip")
        target.write_bytes(archive_bytes)

    install_verified_rtk(
        manifests,
        _windows_context(tmp_path),
        destination,
        machine="AMD64",
        fetch=fetch,
    )

    assert destination.read_bytes() == b"rtk-fixture"
    assert not (destination.parent / "README.txt").exists()


def test_rtk_checksum_mismatch_never_creates_destination(tmp_path: Path) -> None:
    manifests = load_manifests()
    destination = tmp_path / "managed" / "rtk.exe"

    def fetch(_url: str, target: Path) -> None:
        target.write_bytes(b"tampered")

    with pytest.raises(ToolBootstrapError, match="checksum mismatch"):
        install_verified_rtk(
            manifests,
            _windows_context(tmp_path),
            destination,
            machine="AMD64",
            fetch=fetch,
        )

    assert destination.exists() is False
