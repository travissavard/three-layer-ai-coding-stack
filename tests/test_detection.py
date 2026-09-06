from pathlib import Path

from three_layer_installer.detection import detect_clients, detect_project_languages
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId
from three_layer_installer.paths import PathContext, PlatformKind


def test_client_is_detected_by_executable(tmp_path: Path) -> None:
    context = PathContext(PlatformKind.LINUX, tmp_path, {})

    detections = detect_clients(
        load_manifests(),
        context,
        which=lambda name: "/usr/bin/claude" if name == "claude" else None,
    )

    assert detections[ClientId.CLAUDE].detected is True
    assert detections[ClientId.CLAUDE].executable == Path("/usr/bin/claude")


def test_client_version_is_probed_without_starting_an_agent(tmp_path: Path) -> None:
    context = PathContext(PlatformKind.LINUX, tmp_path, {})
    probes: list[tuple[Path, tuple[str, ...]]] = []

    def version_probe(executable: Path, args: tuple[str, ...]) -> str:
        probes.append((executable, args))
        return "Claude Code v2.1.263"

    detections = detect_clients(
        load_manifests(),
        context,
        which=lambda name: "/usr/bin/claude" if name == "claude" else None,
        version_probe=version_probe,
    )

    assert detections[ClientId.CLAUDE].version == "2.1.263"
    assert probes == [(Path("/usr/bin/claude"), ("--version",))]


def test_unparseable_client_version_is_recorded_as_unknown(tmp_path: Path) -> None:
    detections = detect_clients(
        load_manifests(),
        PathContext(PlatformKind.LINUX, tmp_path, {}),
        which=lambda name: "/usr/bin/qwen" if name == "qwen" else None,
        version_probe=lambda _executable, _args: "development build",
    )

    assert detections[ClientId.QWEN].version is None


def test_client_is_detected_by_existing_configuration(tmp_path: Path) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text("", encoding="utf-8")
    context = PathContext(PlatformKind.LINUX, tmp_path, {})

    detections = detect_clients(load_manifests(), context, which=lambda _name: None)

    assert detections[ClientId.CODEX].detected is True
    assert config in detections[ClientId.CODEX].config_paths


def test_auto_language_detection_is_bounded_to_selected_project(tmp_path: Path) -> None:
    project = tmp_path / "selected"
    project.mkdir()
    (project / "package.json").write_text("{}", encoding="utf-8")
    source = project / "cmd"
    source.mkdir()
    (source / "main.go").write_text("package main", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Cargo.toml").write_text("[package]", encoding="utf-8")

    assert detect_project_languages(project, load_manifests()) == ("typescript", "go")
