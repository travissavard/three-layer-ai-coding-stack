# Three-Layer AI Coding Stack Installer Design

Date: 2026-09-04

## Goal

Publish a public, cross-platform installer that configures a token-efficient coding-agent stack for supported AI clients without embedding credentials or user-specific paths.

The stack has exactly three functional layers:

1. **RTK** compresses terminal and tool output before it enters an agent's context.
2. **Native LSP** gives an agent semantic code navigation when the agent client exposes LSP operations.
3. **jMunch** provides indexed retrieval through jCodeMunch, jDocMunch, and jDataMunch as one combined layer.

The `.code-index`, `.doc-index`, and `.data-index` directories are backing stores for Layer 3, not separate layers.

## Users and supported platforms

The installer is intended for general users and must not assume a particular username, home directory, repository layout, credential provider, or operating-system package manager.

Supported installer entry points:

- `install.ps1` on Windows.
- `install.sh` on macOS and Linux.

Both entry points invoke one shared installer core so detection, planning, configuration, verification, backup, and restore behavior remain consistent.

## Initial client scope

The initial capability manifest covers:

- Claude Code
- Codex CLI
- GitHub Copilot CLI
- Gemini CLI
- Qwen Code
- Kimi CLI
- Kilo Code
- Kiro CLI and IDE
- Antigravity
- Visual Studio Code

Each integration is independently classified per layer. A client is never advertised as having all three layers merely because one or two layers are available.

The initial expected Layer 2 classifications are:

| Client | LSP classification |
|---|---|
| Claude Code | Native, using official or explicitly configured LSP plugins |
| GitHub Copilot CLI | Native user- or project-level LSP configuration |
| Qwen Code | Native but experimental and version-gated |
| Kilo Code | Native and configuration-gated |
| Kiro CLI/IDE | Native; CLI setup is workspace-scoped and IDE support comes from language extensions |
| Visual Studio Code | Editor-provided through installed language extensions |
| Codex CLI | Unavailable from the client unless a future verified release exposes it |
| Gemini CLI | Unavailable from the client unless a future verified release exposes it |
| Kimi CLI | Unavailable from the client unless a future verified release exposes it |
| Antigravity | Unavailable from the agent interface unless a future verified release exposes it |

The manifest records source URLs, minimum or tested client versions, integration maturity, and the date each capability was last verified. Documentation must distinguish tested, documented, experimental, unavailable, and unverified behavior.

## Simple LSP explanation

User-facing documentation and status output use this explanation or a shorter equivalent:

> LSP lets an AI client ask a programming language's own code analyzer where symbols are defined, used, and typed. The AI CLI must expose LSP tools before an installer can connect them. If the client does not expose those tools, Layer 2 is unavailable from the client; this installer does not simulate it or claim it is active.

This explanation makes responsibility clear: a missing Layer 2 capability is a limitation of the AI client interface, not an installer failure.

## Language-server scope

The first release provides curated language packs for:

- TypeScript and JavaScript
- Python
- Rust
- Go

`--languages auto` inspects only the explicitly selected project directory and detects relevant project markers and file extensions. It installs a language server only when the corresponding trusted runtime or package manager already exists. It never silently installs a full programming-language runtime.

Clients with workspace-only LSP configuration require `--project <path>`. User-scoped LSP configuration is used only where the client officially supports it.

## Repository structure

```text
install.ps1
install.sh
pyproject.toml
src/three_layer_installer/
config/clients.json
config/languages.json
config/versions.json
tests/
docs/architecture.md
docs/support-matrix.md
docs/troubleshooting.md
docs/superpowers/specs/
README.md
SECURITY.md
CONTRIBUTING.md
LICENSE
.github/workflows/ci.yml
```

The shell entry points bootstrap or locate `uv`, then run a portable Python installer core. Layer 3 already requires the Python package ecosystem through `uvx`, so this avoids two divergent configuration engines while retaining native PowerShell and Bash entry points.

## Installer workflow

The default interactive workflow is:

1. Detect the platform, home/config directories, installed clients, prerequisite tools, existing configurations, and selected project languages.
2. Build an in-memory change plan without emitting configuration contents or environment-variable values.
3. Display a client-by-client, layer-by-layer plan.
4. Ask once for confirmation.
5. Create timestamped backups with restrictive local permissions.
6. Install pinned, tested tool versions unless `--latest` is explicitly selected.
7. Merge only keys owned by this installer into supported client configurations.
8. Install and configure available layers.
9. Run non-agent protocol and executable verification.
10. Print a structured result for every client and layer.

Supported modes and options:

- `--dry-run`: calculate and display the plan without writing or installing.
- `--yes`: accept the displayed plan for unattended use.
- `--client <name>`: target one or more clients.
- `--all`: include every supported detected client.
- `--project <path>`: select a workspace for language detection and workspace-scoped LSP setup.
- `--languages auto|<list>`: select language-server packs.
- `--latest`: opt out of tested pins and request current upstream releases.
- `--verify`: perform checks without configuration changes.
- `--restore <backup-id>`: restore exactly one recorded backup set.

Malformed or unsupported configuration causes that adapter to fail closed. It must not replace or truncate the original file. Re-running the installer is idempotent.

## Layer behavior

### Layer 1: RTK

RTK is installed once. Each client adapter then chooses the strongest verified integration that client supports:

- Native command-rewrite hook.
- Native RTK initialization or integration.
- Concise routing instructions when no compatible hook interface exists.

The final report distinguishes transparent interception from instruction-only routing. RTK's own savings estimates must not be described as billing savings or as an additive total-token percentage.

### Layer 2: native LSP

The installer installs/configures a language server only when all of these are true:

- The selected client has a verified native LSP interface.
- The client version satisfies the manifest gate.
- The language's runtime/package manager is present.
- A user-scoped or selected workspace configuration location is valid.

The verifier may start a language-server process directly and exercise JSON-RPC initialization, symbols, definition, references, and hover operations against a disposable fixture. It does not launch an AI agent or claim that a client consumed those operations unless that fact can be verified through the client's documented non-agent status interface.

### Layer 3: jMunch

Layer 3 consists of three MCP servers installed/configured together:

- jCodeMunch for source-code structure and symbol retrieval.
- jDocMunch for documentation retrieval.
- jDataMunch for structured data retrieval.

The default transport uses pinned packages launched through `uvx`. Each server is verified independently at the MCP protocol level, but the report groups them under one Layer 3 heading and shows component-level failures beneath it.

Indexing is on demand. The installer does not recursively index a home directory or upload index data.

## Status model

Every client/layer result uses one of these statuses:

- `ACTIVE`: configured and verification passed.
- `CONFIGURED`: configuration was installed but client-side runtime proof requires the user to restart or open a workspace.
- `GUIDANCE ONLY`: the tool is installed and routing instructions were added, but transparent interception is unavailable.
- `EXPERIMENTAL`: configured through a client feature explicitly documented as experimental.
- `UNAVAILABLE FROM CLIENT`: the AI client does not expose the required integration.
- `SKIPPED`: intentionally not selected or a prerequisite was absent and the user declined installation.
- `FAILED`: an attempted installation or verification failed, with a remediation message.

Status output must not collapse `CONFIGURED`, `EXPERIMENTAL`, or `GUIDANCE ONLY` into `ACTIVE`.

## Configuration preservation and rollback

- Resolve paths from platform APIs and documented XDG/application locations; never hard-code a username.
- Parse and validate a configuration before mutation.
- Preserve unrelated keys and use format-aware JSON, JSONC, and TOML handling where needed.
- Never log full configuration documents, tokens, command-line secrets, or environment values.
- Store backups outside the repository in the user's platform-appropriate state directory.
- Restrict backup permissions to the current user where the platform supports it.
- Record file hashes and an operation manifest so restore can reject a mismatched or incomplete backup.
- Restore only files listed in the selected backup manifest.

## Supply-chain and licensing policy

- Fetch only from documented upstream project locations and standard package registries.
- Use pinned, tested versions by default.
- Verify published checksums or signatures when upstream provides them.
- Show the source URL and planned version before installation.
- Do not bypass platform trust, execution-policy, workspace-trust, or package-signing controls.
- License this repository's original code under MIT.
- Keep third-party software under its own license and link to current terms.
- Prominently warn users to check current jMunch licensing before commercial use.

## Documentation requirements

The README must include:

- A concise diagram of the three layers and their separate responsibilities.
- A quick start for PowerShell and Bash.
- Prerequisites and exactly what the installer changes.
- The per-client support matrix and verification meanings.
- The simple LSP explanation and client-responsibility caveat.
- Language-pack selection and workspace-scoped setup.
- Dry-run, unattended, verify, and restore examples.
- Privacy, local-index, secrets, licensing, and token-savings caveats.
- Troubleshooting and safe uninstall/restore paths.

Examples use generic paths and placeholder repository names only.

## Testing and verification

Automated tests run against temporary fake home directories and fixture configurations. They must never touch the invoking user's live client configuration.

Required coverage:

- Client and language manifest schema validation.
- Platform path resolution for Windows, macOS, and Linux.
- Detection with clients present, absent, old, and unknown.
- JSON, JSONC, and TOML merge preservation.
- Malformed-config fail-closed behavior.
- Initial apply, repeat/idempotence, partial failure, and exact restore.
- Redaction and non-disclosure of secret-like fixture values.
- Dry-run produces no filesystem mutation.
- Correct jMunch MCP command construction for all adapters.
- LSP protocol smoke fixtures for supported language packs.
- Shell syntax and static analysis for PowerShell, Bash, and Python.
- Repository and Git-history secret scans.

CI runs on current Windows, macOS, and Ubuntu GitHub-hosted runners. Network-dependent integration checks are separated from deterministic unit tests and must not require AI-client authentication.

Before publication, validation includes a clean-clone dry run and a review of the complete Git diff and history for personal paths, credentials, generated files, and accidental local artifacts.

## Non-goals

- Installing or authenticating AI clients.
- Collecting telemetry or usage data.
- Guaranteeing a particular token or billing reduction.
- Simulating LSP for clients that do not expose it.
- Installing full programming-language runtimes without explicit user action.
- Indexing arbitrary directories automatically.
- Accepting third-party license terms on a user's behalf.
- Modifying project source code unrelated to optional workspace LSP configuration.

## Acceptance criteria

The work is complete when:

1. Both entry points provide equivalent plan, apply, verify, and restore behavior on their supported operating systems.
2. All ten client adapters produce correct layer classifications from fixtures.
3. Existing unrelated configuration and secret-like values survive apply and restore without appearing in output.
4. jCodeMunch, jDocMunch, and jDataMunch are installed and reported as one Layer 3.
5. LSP is installed only for clients and versions that expose it, with unsupported clients clearly attributed to client capability.
6. Deterministic tests pass on Windows, macOS, and Linux CI.
7. The README is generalized, source-linked, and contains no user-specific details.
8. Secret scans of the working tree and complete initial Git history pass.
9. A clean clone passes the documented dry-run and verification smoke checks.
10. The repository is publicly accessible on GitHub at the approved target.

## Rollback

Installer changes are reversed with `--restore <backup-id>`. If installation is interrupted, the operation journal identifies completed mutations and offers restoration on the next run. Repository publication can be corrected with ordinary additive commits; published history will not be rewritten to conceal secrets, so the pre-publication secret scan is a hard gate.
