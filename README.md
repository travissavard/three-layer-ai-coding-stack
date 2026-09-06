# Three-Layer AI Coding Stack

A cross-platform, all-in-one installer for a token-efficient AI coding setup on Windows,
macOS, and Linux.

The stack has exactly three functional layers:

| Layer | Purpose | Installed component |
| --- | --- | --- |
| 1 | Compact noisy shell, Git, test, build, package-manager, and log output | [RTK](https://github.com/rtk-ai/rtk) |
| 2 | Let an AI client ask language tools for definitions, references, symbols, types, and diagnostics | The client's native/editor LSP integration, where exposed |
| 3 | Retrieve small, relevant slices of source, documentation, and data instead of loading whole files | jCodeMunch + jDocMunch + jDataMunch as one jMunch layer |

```text
AI coding client
  -> Layer 1: RTK output compression
  -> Layer 2: native/editor LSP (when the client exposes it)
  -> Layer 3: jMunch indexed retrieval
       |- jCodeMunch -> .code-index
       |- jDocMunch  -> .doc-index
       `- jDataMunch -> .data-index
```

`.code-index`, `.doc-index`, and `.data-index` are backing stores created and managed by the
jMunch tools. They are not additional layers, and this installer does not pre-index a user's
projects.

## Important jMunch licensing notice

jCodeMunch, jDocMunch, and jDataMunch are separately licensed products. Their free license
terms cover qualifying non-commercial use only. Commercial use requires the applicable paid
license from the publisher. This project does not sell, grant, or validate those licenses.

Before Layer 3 is configured, choose exactly one declaration:

- `--jmunch-use noncommercial` — you have reviewed the terms and your use qualifies.
- `--jmunch-use commercial-licensed` — you already hold the required commercial license.
- `--jmunch-use skip` — do not configure any jMunch component.

Unattended installs using `--yes` require one of these declarations. Interactive installs show
the component versions and license links before asking. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the full attribution inventory.

## Quick start

Clone the repository first so the pinned lockfile, manifests, and checksummed bootstrap data are
installed together:

```bash
git clone https://github.com/travissavard/three-layer-ai-coding-stack.git
cd three-layer-ai-coding-stack
```

Windows PowerShell:

```powershell
.\install.ps1 --client claude --jmunch-use noncommercial
```

macOS or Linux:

```bash
./install.sh --client claude --jmunch-use noncommercial
```

Replace `noncommercial` with `commercial-licensed` only if you hold the applicable paid
licenses, or with `skip` to install without Layer 3. Omit `--client` to configure all supported
AI clients detected on `PATH` or through an existing supported configuration file.

To configure Layer 2 as well, add `--languages python` (or another supported pack), or supply
`--project` with your project directory and `--languages auto`. The installer otherwise leaves
language selection empty.

Preview the planned configuration changes:

```bash
./install.sh --all --project /path/to/project --languages auto --dry-run
```

The equivalent PowerShell command uses `.\install.ps1` and a Windows project path.

## Requirements

- Windows 10/11, macOS, or Linux on x86-64 or ARM64.
- An internet connection for the first run and for components not already installed.
- At least one supported AI client installed and available on `PATH`.
- Node.js/npm for the TypeScript/JavaScript or Python LSP packs.
- Go for the Go LSP pack, or Rust tooling for the Rust LSP pack.
- Bash and the dependencies required by the selected client's RTK hook integration (including
  Git Bash on Windows where shell scripts are used).

The launchers use an existing `uv` when present. Otherwise they download the pinned `uv`
release to a temporary directory, verify its SHA-256 checksum, and run the locked installer
environment. uv may obtain Python when needed. Even a dry-run may download this temporary
bootstrap environment; it does not install the target tools or write client configuration.
Existing RTK and language-server executables are reused by default; newly downloaded RTK and
newly installed registry language packs use the manifest pins. RTK currently has no
Windows ARM64 artifact in the pinned release, so Layer 1 cannot be installed natively on that
combination; the installer reports the failure without substituting an unverified binary.

## Supported clients

| AI client | Layer 1: RTK | Layer 2: LSP | Layer 3: jMunch |
| --- | --- | --- | --- |
| Claude Code | Native user integration | Native: TypeScript/JavaScript, Python, Rust | MCP |
| Codex CLI | User instructions via RTK init | **UNAVAILABLE FROM CLIENT** | MCP |
| GitHub Copilot CLI | Native user integration | Native: TypeScript/JavaScript, Python, Rust, Go | MCP |
| Gemini CLI | Native user integration | **UNAVAILABLE FROM CLIENT** | MCP |
| Qwen Code | Guidance | Experimental project integration | MCP |
| Kimi CLI | Project instructions via RTK init | **UNAVAILABLE FROM CLIENT** | MCP |
| Kilo Code | Project guidance in AGENTS.md | Native: TypeScript/JavaScript, Python, Rust, Go | MCP |
| Kiro CLI/IDE | Guidance | Native project integration | MCP |
| Antigravity | Project instructions via RTK init | **UNAVAILABLE FROM CLIENT** | MCP |
| Visual Studio Code | Native user integration | Editor-managed; no standalone server is written | MCP |

Instruction-based routing is reported as `GUIDANCE ONLY`: the agent must follow the instructions
and prefix its commands with `rtk`. Hook integrations remain `CONFIGURED` until the client reloads
them. Project-scoped RTK integrations require `--project`. Kilo targets the current CLI-backed
configuration format; Kiro's language-server configuration targets its CLI, while the IDE manages
language support through its extensions.

The matrix reflects documented client capabilities verified on 2026-09-06. Upstream clients can
change. Exact primary-source links live in [config/clients.json](config/clients.json), and a more
detailed matrix is in [docs/support-matrix.md](docs/support-matrix.md).

### What LSP means

LSP stands for Language Server Protocol. In simple terms, it is the same kind of code awareness
an editor uses for “go to definition,” references, type information, and error diagnostics. When
an AI CLI exposes native agent-facing LSP tools, the installer can connect a verified language
server pack to them.

When the table says **UNAVAILABLE FROM CLIENT**, Layer 2 is unavailable because that AI client
does not expose a supported agent-facing LSP interface. It is not a missing feature in this
installer, and installing a language server alone cannot add that interface to the client. For
Visual Studio Code, the editor already owns language-server support, so the installer leaves it
alone instead of creating a duplicate standalone configuration.

## Language packs

Available packs are:

- `typescript` — TypeScript and JavaScript via `typescript-language-server`
- `python` — Python via Pyright
- `rust` — Rust via rust-analyzer
- `go` — Go via gopls

Use a comma-separated list or project auto-detection:

```bash
./install.sh --client copilot --languages typescript,python --jmunch-use skip
./install.sh --client kilo --project /path/to/project --languages auto --jmunch-use noncommercial
```

Without `--project`, the default is no LSP language packs. With `--project`, the default is
`--languages auto`, which checks common project markers. A client can still support fewer packs
than the requested list; unsupported pairs are reported as skipped.

Native LSP requires a verified client version. The configured minimum versions are Claude Code
2.0.74, Copilot CLI 0.0.405, Qwen Code 0.9.0, Kilo 1.0.0, and Kiro CLI 1.22.0. An older or unknown
version is reported as skipped. Sources are linked in the support matrix. Qwen must be started
with `--experimental-lsp` after configuration. Rust uses the active rustup toolchain's
rust-analyzer component, including in `--latest` mode; the installer does not update that toolchain.

## Installer modes and options

```text
--client CLIENT       Select one client; repeat for multiple clients
--all                 Select every supported detected client
--project PATH        Enable project-scoped integrations and language detection
--languages LIST      auto, none, or comma-separated language pack names
--jmunch-use BASIS    noncommercial, commercial-licensed, or skip
--latest              Opt out of tested pins and request current upstream releases
--dry-run             Print the plan without target-tool installs or configuration changes
--yes                 Confirm the plan non-interactively (requires a jMunch declaration)
--verify              Check the selected stack without changing configuration
--restore BACKUP_ID   Restore files from a prior installer operation
--licenses            Print the complete component license inventory
```

Examples:

```bash
# Preview every detected client.
./install.sh --dry-run

# Configure all detected clients without Layer 3.
./install.sh --all --jmunch-use skip --yes

# Verify Claude Code's configured layers.
./install.sh --client claude --verify --jmunch-use noncommercial

# Print licenses without installing.
./install.sh --licenses

# Restore a prior operation.
./install.sh --restore OPERATION_ID
```

On PowerShell, replace `./install.sh` with `.\install.ps1`.

Pinned versions are the recommended default. `--latest` deliberately opts out of tested pins for
RTK, language servers, and jMunch packages. The plan labels them as untested latest requests and
links their registries. RTK latest-mode queries GitHub's official release API and proceeds only
when GitHub provides a valid SHA-256 digest for the exact platform asset. Registry packages use
their normal highest stable resolution. Current releases can change behavior or license terms, so
review the displayed sources and controlling terms before confirming.

## Safe changes and restore

Before applying a plan, the installer snapshots every configuration path it owns. Existing JSON,
JSONC, and TOML files are merged rather than replaced. A backup operation ID is printed after a
successful change and after a failed change that reached the backup stage.

Restore is hash-guarded: it refuses to overwrite files that changed after installation. This
protects later edits instead of silently discarding them. Backups are local to the current user;
no configuration or project contents are uploaded by this installer.

Backups can contain credentials already present in a client configuration. Keep the per-user
state directory private and never attach it to a public issue. Restore reverses recorded files
and managed tool directories; it does not uninstall shared npm/Go/rustup language packages or
remove downloaded Claude plugin caches and package-manager caches. Claude plugin settings and
its installed-plugin registry are recorded.

If RTK was downloaded into installer storage, add the printed managed `bin` directory to your
user `PATH`, then restart your terminal and AI client. Native hooks invoke `rtk` by name, so this
step is required before they can run. The installer does not edit shell profiles or the Windows
registry. See the platform paths in [troubleshooting](docs/troubleshooting.md#rtk-is-not-on-path).

Verification reads the saved configuration and directly probes MCP/LSP server processes. A first
`uvx` probe can download packages and populate its cache. `ACTIVE` for Layer 3 means the saved
configuration and server protocols passed; it does not prove that a running AI session loaded
them. Restart the client and allow the servers through its normal trust prompts.

## Privacy and token-savings claims

The installer adds no telemetry. It disables RTK telemetry during setup and disables the jMunch
tools' optional savings reporting in generated MCP environments. The individual tools and AI
clients remain separate software with their own behavior and terms; review those projects before
use.

Token savings depend on repositories, commands, prompts, and client behavior. Any savings shown
by a component are estimates, not billing records or guaranteed reductions.

## Troubleshooting

Run a dry-run first, then use `--verify` after installation. Common dependency, client-detection,
LSP, backup, and restore issues are covered in [docs/troubleshooting.md](docs/troubleshooting.md).
The design and security boundaries are described in [docs/architecture.md](docs/architecture.md).

## Development

```bash
uv sync --frozen
uv run pytest --cov=three_layer_installer --cov-fail-under=80
uv run ruff check .
uv run mypy src tests
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before submitting changes or
reporting a vulnerability.

## License

This installer is licensed under the [MIT License](LICENSE). Third-party tools are not relicensed
by this project; their own licenses and service terms continue to apply. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
