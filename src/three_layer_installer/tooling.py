"""Resolve and safely install the small bootstrap toolchain."""

from __future__ import annotations

import hashlib
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

from .backup import atomic_write
from .manifests import ManifestSet
from .paths import PathContext, PlatformKind

_MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
_MAX_BINARY_BYTES = 100 * 1024 * 1024


class ToolBootstrapError(RuntimeError):
    """A managed tool could not be obtained or verified safely."""


@dataclass(frozen=True)
class Toolchain:
    rtk_command: str
    uv_command: str | None
    uvx_command: str | None
    managed_targets: tuple[Path, ...]
    bootstrap_uv_sources: tuple[tuple[Path, Path], ...]
    rtk_install_required: bool


def _executable_name(name: str, context: PathContext) -> str:
    return f"{name}.exe" if context.platform is PlatformKind.WINDOWS else name


def resolve_toolchain(
    context: PathContext,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> Toolchain:
    """Resolve system tools, previous managed tools, and launcher-provided uv."""

    managed_bin = context.state_root / "bin"
    rtk_target = managed_bin / _executable_name("rtk", context)
    uv_target = managed_bin / _executable_name("uv", context)
    uvx_target = managed_bin / _executable_name("uvx", context)
    managed_targets: list[Path] = []
    bootstrap_sources: list[tuple[Path, Path]] = []

    if which("rtk"):
        rtk_command = "rtk"
        rtk_install_required = False
    elif rtk_target.is_file():
        rtk_command = str(rtk_target.resolve())
        rtk_install_required = False
    else:
        rtk_command = str(rtk_target.resolve())
        rtk_install_required = True
        managed_targets.append(rtk_target)

    if which("uv") and which("uvx"):
        uv_command: str | None = "uv"
        uvx_command: str | None = "uvx"
    elif uv_target.is_file() and uvx_target.is_file():
        uv_command = str(uv_target.resolve())
        uvx_command = str(uvx_target.resolve())
    else:
        bootstrap_value = context.environment.get("THREE_LAYER_BOOTSTRAP_UV_DIR")
        bootstrap_dir = Path(bootstrap_value).resolve() if bootstrap_value else None
        uv_source = (
            bootstrap_dir / _executable_name("uv", context) if bootstrap_dir else None
        )
        uvx_source = (
            bootstrap_dir / _executable_name("uvx", context) if bootstrap_dir else None
        )
        if uv_source and uvx_source and uv_source.is_file() and uvx_source.is_file():
            uv_command = str(uv_target.resolve())
            uvx_command = str(uvx_target.resolve())
            managed_targets.extend((uv_target, uvx_target))
            bootstrap_sources.extend(((uv_source, uv_target), (uvx_source, uvx_target)))
        else:
            uv_command = "uv" if which("uv") else None
            uvx_command = "uvx" if which("uvx") else None

    return Toolchain(
        rtk_command=rtk_command,
        uv_command=uv_command,
        uvx_command=uvx_command,
        managed_targets=tuple(dict.fromkeys(path.resolve() for path in managed_targets)),
        bootstrap_uv_sources=tuple(bootstrap_sources),
        rtk_install_required=rtk_install_required,
    )


def materialize_bootstrap_uv(toolchain: Toolchain) -> None:
    """Copy only the verified launcher's uv binaries into installer-owned storage."""

    for source, destination in toolchain.bootstrap_uv_sources:
        if not source.is_file():
            raise ToolBootstrapError(f"bootstrap executable disappeared: {source.name}")
        atomic_write(destination, source.read_bytes(), mode=0o755)


def _asset_key(context: PathContext, machine: str) -> str:
    normalized = machine.lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    if normalized not in {"x86_64", "arm64"}:
        raise ToolBootstrapError(f"unsupported processor architecture: {machine}")
    return f"{context.platform.value}-{normalized}"


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "three-layer-installer/0.1"})
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > _MAX_ARCHIVE_BYTES:
                    raise ToolBootstrapError("RTK archive exceeds the safety size limit")
                out.write(chunk)
    except ToolBootstrapError:
        raise
    except OSError as exc:
        raise ToolBootstrapError(f"RTK download failed: {type(exc).__name__}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_limited(stream: IO[bytes]) -> bytes:
    value = stream.read(_MAX_BINARY_BYTES + 1)
    if len(value) > _MAX_BINARY_BYTES:
        raise ToolBootstrapError("RTK executable exceeds the safety size limit")
    return value


def _safe_member_name(value: str) -> PurePosixPath:
    name = PurePosixPath(value.replace("\\", "/"))
    if name.is_absolute() or ".." in name.parts:
        raise ToolBootstrapError("RTK archive contains an unsafe path")
    return name


def _binary_from_zip(archive_path: Path, executable_name: str) -> bytes:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            matches = []
            for info in archive.infolist():
                member = _safe_member_name(info.filename)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ToolBootstrapError("RTK archive contains a symbolic link")
                if not info.is_dir() and member.name == executable_name:
                    matches.append(info)
            if len(matches) != 1:
                raise ToolBootstrapError("RTK archive must contain exactly one executable")
            with archive.open(matches[0]) as stream:
                return _read_limited(stream)
    except zipfile.BadZipFile as exc:
        raise ToolBootstrapError("RTK release is not a valid zip archive") from exc


def _binary_from_tar(archive_path: Path, executable_name: str) -> bytes:
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            matches = []
            for member in archive.getmembers():
                name = _safe_member_name(member.name)
                if member.issym() or member.islnk():
                    raise ToolBootstrapError("RTK archive contains a link")
                if member.isfile() and name.name == executable_name:
                    matches.append(member)
            if len(matches) != 1:
                raise ToolBootstrapError("RTK archive must contain exactly one executable")
            stream = archive.extractfile(matches[0])
            if stream is None:
                raise ToolBootstrapError("RTK executable could not be read")
            with stream:
                return _read_limited(stream)
    except tarfile.TarError as exc:
        raise ToolBootstrapError("RTK release is not a valid tar archive") from exc


def install_verified_rtk(
    manifests: ManifestSet,
    context: PathContext,
    destination: Path,
    *,
    machine: str | None = None,
    fetch: Callable[[str, Path], None] = _download,
) -> None:
    """Download a pinned RTK release, verify its digest, and install one binary."""

    definition = manifests.bootstrap.get("rtk")
    if not isinstance(definition, dict):
        raise ToolBootstrapError("RTK bootstrap metadata is missing")
    assets = definition.get("assets")
    key = _asset_key(context, machine or platform.machine())
    asset = assets.get(key) if isinstance(assets, dict) else None
    if not isinstance(asset, dict):
        raise ToolBootstrapError(f"RTK has no verified release asset for {key}")
    name = asset.get("name")
    expected = asset.get("sha256")
    base_url = definition.get("base_url")
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or not isinstance(expected, str)
        or len(expected) != 64
        or not isinstance(base_url, str)
        or not base_url.startswith("https://github.com/rtk-ai/rtk/releases/download/")
    ):
        raise ToolBootstrapError("RTK bootstrap metadata is invalid")

    with tempfile.TemporaryDirectory(prefix="three-layer-rtk-") as temporary:
        archive_path = Path(temporary) / name
        fetch(f"{base_url.rstrip('/')}/{name}", archive_path)
        if not archive_path.is_file():
            raise ToolBootstrapError("RTK download did not produce an archive")
        actual = _sha256(archive_path)
        if actual.lower() != expected.lower():
            raise ToolBootstrapError(
                f"RTK archive checksum mismatch; expected {expected}, received {actual}"
            )
        executable_name = _executable_name("rtk", context)
        binary = (
            _binary_from_zip(archive_path, executable_name)
            if name.endswith(".zip")
            else _binary_from_tar(archive_path, executable_name)
        )
        atomic_write(destination, binary, mode=0o755)
