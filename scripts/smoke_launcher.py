"""Run a launcher dry-run with an empty home and a PATH containing no AI clients."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from three_layer_installer.manifests import load_manifests
from three_layer_installer.paths import PathContext, PlatformKind, configured_path_templates

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    uv = shutil.which("uv")
    shell = shutil.which("pwsh" if os.name == "nt" else "bash")
    if uv is None or shell is None:
        raise SystemExit("The launcher smoke check requires uv and PowerShell/Bash")
    with tempfile.TemporaryDirectory(prefix="three-layer-launcher-") as temporary:
        root = Path(temporary)
        executable = root / ("uv.exe" if os.name == "nt" else "uv")
        shutil.copy2(uv, executable)
        environment = dict(os.environ)
        environment.update(
            {
                "HOME": str(root / "fake-home"),
                "USERPROFILE": str(root / "fake-home"),
                "APPDATA": str(root / "fake-home" / "Roaming"),
                "LOCALAPPDATA": str(root / "fake-home" / "Local"),
                "XDG_CONFIG_HOME": str(root / "fake-home" / "config"),
                "XDG_STATE_HOME": str(root / "fake-home" / "state"),
            }
        )
        for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "COPILOT_HOME"):
            environment.pop(name, None)
        environment.pop("VIRTUAL_ENV", None)
        system_paths = (
            [str(Path(os.environ["SYSTEMROOT"]) / "System32")]
            if os.name == "nt"
            else ["/usr/bin", "/bin"]
        )
        environment["PATH"] = os.pathsep.join([str(root), *system_paths])
        for client in (
            "claude",
            "codex",
            "copilot",
            "gemini",
            "qwen",
            "kimi",
            "kilo",
            "kiro",
            "kiro-cli",
            "antigravity",
            "code",
        ):
            if shutil.which(client, path=environment["PATH"]):
                raise SystemExit("The isolated smoke PATH contains an AI client; refusing to run")
        command = (
            [shell, "-NoProfile", "-File", str(ROOT / "install.ps1")]
            if os.name == "nt"
            else [shell, str(ROOT / "install.sh")]
        )
        subprocess.run(
            [*command, "--client", "claude", "--jmunch-use", "skip", "--dry-run"],
            cwd=root,
            env=environment,
            check=True,
            timeout=180,
        )
        context = PathContext(PlatformKind.current(), root / "fake-home", environment)
        for definition in load_manifests().clients["clients"].values():
            for template in configured_path_templates(definition, context.platform):
                assert not context.resolve(template).exists(), "Dry-run wrote client configuration"
        assert not context.state_root.exists(), "Dry-run wrote installer state"
        artifacts = [str(path.relative_to(context.home)) for path in context.home.rglob("*")]
        if artifacts:
            print("Temporary shell/bootstrap artifacts: " + ", ".join(artifacts))
    print("Isolated launcher dry-run passed")


if __name__ == "__main__":
    main()
