from pathlib import Path

from three_layer_installer.paths import PathContext, PlatformKind


def test_windows_template_expands_appdata(tmp_path: Path) -> None:
    context = PathContext(
        platform=PlatformKind.WINDOWS,
        home=tmp_path,
        environment={"APPDATA": str(tmp_path / "Roaming")},
    )

    assert context.resolve("%APPDATA%/Code/User/mcp.json") == (
        tmp_path / "Roaming" / "Code" / "User" / "mcp.json"
    )


def test_linux_xdg_template_uses_config_fallback(tmp_path: Path) -> None:
    context = PathContext(platform=PlatformKind.LINUX, home=tmp_path, environment={})

    assert context.resolve("${XDG_CONFIG_HOME:-~/.config}/kilo/kilo.jsonc") == (
        tmp_path / ".config" / "kilo" / "kilo.jsonc"
    )


def test_state_root_is_platform_appropriate(tmp_path: Path) -> None:
    windows = PathContext(
        platform=PlatformKind.WINDOWS,
        home=tmp_path,
        environment={"LOCALAPPDATA": str(tmp_path / "Local")},
    )
    linux = PathContext(platform=PlatformKind.LINUX, home=tmp_path, environment={})
    macos = PathContext(platform=PlatformKind.MACOS, home=tmp_path, environment={})

    assert windows.state_root == tmp_path / "Local" / "three-layer-ai-coding-stack"
    assert linux.state_root == tmp_path / ".local" / "state" / "three-layer-ai-coding-stack"
    assert macos.state_root == (
        tmp_path / "Library" / "Application Support" / "three-layer-ai-coding-stack"
    )

