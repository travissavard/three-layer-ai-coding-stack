from importlib.util import find_spec
from pathlib import Path


def test_installer_package_is_importable() -> None:
    assert find_spec("three_layer_installer") is not None


def test_packaging_readme_exists() -> None:
    assert Path("README.md").is_file()
