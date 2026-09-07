# Live validation boundaries

The deterministic test suite is not a complete end-to-end certification.
The opt-in `Live tool integration (not client E2E)` workflow adds real downloads,
real launcher execution, actual RTK commands, reinstall/restore, and meaningful
language-server queries on GitHub-hosted Windows, macOS, and Linux machines.

Run the component tests on Linux/macOS with Node.js, Git, Python, and uv installed:

```bash
uv sync --frozen
uv run --frozen python scripts/live_tools.py
```

Add `--languages typescript,python,go,rust` when Go and rustup are installed.
The harness downloads the manifest's actual language-server packages into
temporary npm/Go/Rust directories.
It requires nonempty symbol, definition, reference, and hover results for known
fixture functions. Actual AI-client consumption is not covered by this
harness. LSP is supplied by the AI client/editor; a working server does not give
LSP tools to a client that does not expose them.

Rust testing copies only the prerequisite rustup executable, installs a minimal
stable toolchain plus `rust-src` in isolated `RUSTUP_HOME`/`CARGO_HOME` directories,
and runs the manifest's `rustup component add rust-analyzer` command. Component
inventories prove a fresh install; the report records the resolved versions
because the manifest deliberately follows the active rustup toolchain. A
dependency-free Cargo fixture is tested only after the server reports healthy,
quiescent status. Build scripts, procedural macros, and check-on-save are disabled
and remain untested. See [rustup isolation](https://rust-lang.github.io/rustup/installation/index.html#choosing-where-to-install)
and [rust-analyzer readiness](https://rust-analyzer.github.io/book/contributing/lsp-extensions.html#server-status).

Docker provides an additional Linux run without using personal client configs:

```bash
docker build -f scripts/live-tools.Dockerfile -t three-layer-live-tools:verification .
docker run --name three-layer-live-tools three-layer-live-tools:verification
docker cp three-layer-live-tools:/results/linux-docker.json ./linux-docker.json
```

The Docker image includes Node/Python prerequisites. Images, containers, and
temporary profiles are retained for inspection; these commands do not remove
existing user environments. Downloading packages requires network access.

## Important Windows isolation limitation

RTK 0.48.0 resolves some paths through Windows' native user-profile API, ignoring
the `HOME`/`USERPROFILE` overrides used by a temporary-profile harness. An environment
variable override is therefore **not** a Windows sandbox. The harness refuses to
run native global RTK setup on a normal Windows workstation. Its Windows test
requires `--ci-native-home` on an ephemeral GitHub-hosted runner, where the entire
Windows user profile is disposable. Do not set `GITHUB_ACTIONS` locally to bypass
that guard, or run this workflow on a persistent/self-hosted runner.

## What the results mean

- Seeded client config files exercise the installer's supported config-detection
  and adapter paths. They are not installed or simulated AI clients.
- No AI CLI, model endpoint, user credential, or paid model call is used.
- jMunch is explicitly skipped. This workflow does not declare a noncommercial
  or paid commercial license basis on anyone's behalf.
- Restore checks compare every owned file against its pre-install SHA-256 or
  expected absence, compare the complete client config trees, and check an
  unrelated sentinel file. A separate check edits a fixture and proves restore
  refuses it without changing any client config. This does not establish
  restore after a full jMunch/plugin installation or after a client edits config.
- A report's `passed: true` means its **component** checks passed.
  `full_end_to_end` remains `false`; skipped/unproven work is not a pass.

Reports go to `.e2e-results/` (gitignored) and the workflow prints sanitized JSON.
Only controlled fixtures and an allowlisted environment are used. The test root
and repository paths are redacted from saved reports.

## Compatibility finding

Live testing found that `typescript-language-server` 6.0.0 does not work with the
TypeScript 7 package. The upstream server's installation instructions require
TypeScript 6. The verified track now selects TypeScript 6.0.3, and `--latest`
selects the latest **compatible TypeScript 6** alongside the current language
server. This does not upgrade the language-server integration to TypeScript 7's
separate native LSP implementation. See the
[upstream installation instructions](https://github.com/typescript-language-server/typescript-language-server/tree/v6.0.0#installing).

The first real RTK installation also exposed a missing Claude configuration
directory and Gemini's noninteractive refusal to patch existing settings. The
installer now creates Claude's directory after taking its backup and passes
Gemini's explicit auto-patch option after the installer confirmation. LF checkout
rules prevent Windows CRLF line endings from breaking the Bash launcher in Docker
or WSL. These fixes were driven by failed real-tool runs, not mock-only checks.

On Windows, gopls rejected a temporary workspace containing the short-name alias
`RUNNER~1`, because Windows reports the actual directory as `runneradmin`. Both
the live harness and the installer's protocol verifier now resolve the temporary
directory to its canonical path before constructing language-server file URIs.

Rust's real server also rejected the verifier's empty-object shutdown parameters.
The shared protocol verifier and live harness now send null parameters for the
parameterless LSP shutdown and exit messages. Regression assertions cover both.
