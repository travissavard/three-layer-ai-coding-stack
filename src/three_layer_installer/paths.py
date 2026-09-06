"""Platform-aware paths without shell expansion."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PlatformKind(str, Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"

    @classmethod
    def current(cls) -> PlatformKind:
        if os.name == "nt":
            return cls.WINDOWS
        if sys.platform == "darwin":
            return cls.MACOS
        return cls.LINUX


_WINDOWS_VARIABLE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_DEFAULT_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}")


@dataclass(frozen=True)
class PathContext:
    platform: PlatformKind
    home: Path
    environment: Mapping[str, str]

    @classmethod
    def current(cls) -> PathContext:
        return cls(PlatformKind.current(), Path.home(), dict(os.environ))

    def resolve(self, template: str) -> Path:
        def windows_value(match: re.Match[str]) -> str:
            name = match.group(1)
            return self.environment.get(name, match.group(0))

        def default_value(match: re.Match[str]) -> str:
            name, default = match.groups()
            return self.environment.get(name) or default

        expanded = _WINDOWS_VARIABLE.sub(windows_value, template)
        expanded = _DEFAULT_VARIABLE.sub(default_value, expanded)
        if expanded == "~":
            expanded = str(self.home)
        elif expanded.startswith(("~/", "~\\")):
            expanded = str(self.home / expanded[2:])
        return Path(expanded.replace("/", os.sep))

    @property
    def state_root(self) -> Path:
        name = "three-layer-ai-coding-stack"
        if self.platform is PlatformKind.WINDOWS:
            base = self.environment.get("LOCALAPPDATA")
            return Path(base) / name if base else self.home / "AppData" / "Local" / name
        if self.platform is PlatformKind.MACOS:
            return self.home / "Library" / "Application Support" / name
        base = self.environment.get("XDG_STATE_HOME")
        return Path(base) / name if base else self.home / ".local" / "state" / name


def configured_path_templates(client: dict[str, object], platform: PlatformKind) -> tuple[str, ...]:
    mcp = client.get("mcp")
    if not isinstance(mcp, dict):
        return ()
    user_paths = mcp.get("user_paths")
    if not isinstance(user_paths, dict):
        return ()
    candidates: list[str] = []
    for key in ("all", platform.value, "current", "legacy"):
        value = user_paths.get(key)
        if isinstance(value, str):
            candidates.append(value)
    return tuple(candidates)
