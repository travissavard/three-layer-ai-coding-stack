import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".sh", ".toml", ".yml", ".yaml"}
IGNORED_PARTS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "dist"}


def repository_text() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in {"LICENSE", ".gitignore"}:
            files[path.relative_to(ROOT)] = path.read_text(encoding="utf-8")
    return files


def test_public_documentation_is_complete() -> None:
    required = {
        Path("README.md"),
        Path("LICENSE"),
        Path("THIRD_PARTY_NOTICES.md"),
        Path("SECURITY.md"),
        Path("CONTRIBUTING.md"),
        Path("docs/architecture.md"),
        Path("docs/support-matrix.md"),
        Path("docs/troubleshooting.md"),
    }

    assert all((ROOT / path).is_file() for path in required)


def test_readme_documents_all_layers_clients_and_license_choices() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.lower().split())

    for layer in ("Layer 1", "Layer 2", "Layer 3"):
        assert layer in readme
    for client in (
        "Claude Code",
        "Codex CLI",
        "GitHub Copilot CLI",
        "Gemini CLI",
        "Qwen Code",
        "Kimi CLI",
        "Kilo Code",
        "Kiro CLI/IDE",
        "Antigravity",
        "Visual Studio Code",
    ):
        assert client in readme
    for index_store in (".code-index", ".doc-index", ".data-index"):
        assert index_store in readme
    for basis in ("noncommercial", "commercial-licensed", "skip"):
        assert f"--jmunch-use {basis}" in readme
    assert "--latest" in readme
    assert "UNAVAILABLE FROM CLIENT" in readme
    assert "LSP stands for Language Server Protocol" in readme
    assert "not a missing feature in this installer" in normalized_readme


def test_third_party_notice_attributes_each_jmunch_license() -> None:
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    normalized_notice = " ".join(notice.lower().split())

    for component in ("jCodeMunch", "jDocMunch", "jDataMunch"):
        assert component in notice
    for license_id in (
        "LicenseRef-jCodeMunch-Dual-Use-1",
        "LicenseRef-jDocMunch-Dual-Use",
        "LicenseRef-jDataMunch-Dual-Use",
    ):
        assert license_id in notice
    assert "paid commercial license" in normalized_notice


def test_repository_text_has_no_personal_home_paths_or_secret_shapes() -> None:
    patterns = {
        "Windows user home": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
        "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        "OpenAI-style secret": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    }

    findings: list[str] = []
    for path, content in repository_text().items():
        for label, pattern in patterns.items():
            if pattern.search(content):
                findings.append(f"{path}: {label}")

    assert findings == []


def test_ci_actions_are_pinned_to_full_commit_shas() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    action_uses = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)

    assert action_uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in action_uses)
