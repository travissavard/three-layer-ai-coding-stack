"""Smoke-test the built wheel outside the source tree, with no real client detection."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""
from pathlib import Path
from three_layer_installer.cli import run
from three_layer_installer.manifests import load_manifests, validate_manifests
from three_layer_installer.paths import PathContext, PlatformKind
assert validate_manifests(load_manifests()) == []
context = PathContext(PlatformKind.current(), Path.cwd() / "fake-home", {})
for mode in ("--dry-run", "--verify"):
    assert run(["--client", "claude", "--jmunch-use", "skip", mode],
               context=context, which=lambda _: None) == 0
assert not context.home.exists()
print("Installed-wheel manifests, dry-run and verify smoke passed")
"""


def main() -> None:
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one wheel before running the smoke check")
    with tempfile.TemporaryDirectory(prefix="three-layer-wheel-") as temporary:
        subprocess.run(
            ["uv", "run", "--no-project", "--with", str(wheels[0]), "python", "-I", "-c", CHECK],
            cwd=temporary,
            check=True,
        )


if __name__ == "__main__":
    main()
