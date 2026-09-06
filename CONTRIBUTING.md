# Contributing

Contributions should preserve the installer’s three-layer model, cross-platform behavior, license
disclosures, and reversible configuration guarantees.

## Development setup

Install [uv](https://docs.astral.sh/uv/), clone the repository, and create the locked environment:

```bash
uv sync --frozen
```

Run the required checks:

```bash
uv run pytest --cov=three_layer_installer --cov-fail-under=80
uv run ruff check .
uv run mypy src tests
uv build
```

Also validate the launcher syntax on the operating system you change:

```bash
bash -n install.sh
```

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path .\install.ps1),
    [ref] $null,
    [ref] $errors
) | Out-Null
if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }
```

## Change rules

- Add a failing test before changing behavior, then prove it passes.
- Preserve unrelated configuration and user-owned worktree changes.
- Keep client and platform behavior manifest-driven.
- Use official/primary documentation for integration claims and record the URL plus verification
  date in `config/clients.json`.
- Pin executable and package versions. Update checksums from independently verified release
  artifacts when a downloaded asset changes.
- Update `THIRD_PARTY_NOTICES.md` and `config/licenses.json` when a dependency, version, license,
  commercial tier, or service term changes.
- Never add credentials, personal paths, telemetry, unrequested network services, or fixtures
  containing real user configuration.
- Keep `UNAVAILABLE FROM CLIENT` exact for AI clients that lack an agent-facing LSP interface.
- Treat jCodeMunch, jDocMunch, and jDataMunch as one functional layer while preserving their
  separate license declarations and attributions.

## Pull requests

Use a focused branch and Conventional Commit messages. A pull request should explain the outcome,
affected clients/platforms, tests performed, license or supply-chain impact, and rollback behavior.
Include no generated environments, caches, jMunch index stores, backups, or secrets.

By contributing, you agree that your contribution is licensed under this repository's MIT License.
