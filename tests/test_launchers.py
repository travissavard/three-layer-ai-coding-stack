from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_powershell_launcher_is_pinned_verified_and_forwards_arguments() -> None:
    script = (ROOT / "install.ps1").read_text(encoding="utf-8")

    assert "0.12.10" in script
    assert "Get-FileHash" in script
    assert "f65744f94072152b1f86ba2aace4d01f1124d9a8ecb235805039e3718c36cac2" in script
    assert "@InstallerArgs" in script
    assert "--frozen" in script
    assert "Invoke-Expression" not in script


def test_bash_launcher_is_pinned_verified_and_forwards_arguments() -> None:
    script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash\n")
    assert "0.12.10" in script
    assert "sha256sum" in script and "shasum" in script
    assert "173d95a0c32d18c896c46ba6fafbf3cf9c14ab74b033f81b76c883ef492a976b" in script
    assert '"$@"' in script
    assert "--frozen" in script
    assert "| sh" not in script


def test_launchers_use_ephemeral_uv_state_even_when_uv_exists() -> None:
    powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
    bash = (ROOT / "install.sh").read_text(encoding="utf-8")

    for variable in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PROJECT_ENVIRONMENT"):
        assert variable in powershell
        assert variable in bash
