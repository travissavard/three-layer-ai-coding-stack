from importlib.util import find_spec
from pathlib import Path


def test_installer_package_is_importable() -> None:
    assert find_spec("three_layer_installer") is not None


def test_packaging_readme_exists() -> None:
    assert Path("README.md").is_file()


def test_package_declares_inline_typing_support() -> None:
    assert Path("src/three_layer_installer/py.typed").is_file()
