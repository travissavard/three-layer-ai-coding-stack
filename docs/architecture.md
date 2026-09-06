# Architecture

## Purpose

The installer configures three complementary ways for supported AI coding clients to consume
less irrelevant context:

1. RTK compacts command output before it reaches the model.
2. A client's native/editor LSP integration provides precise code intelligence, where available.
3. jCodeMunch, jDocMunch, and jDataMunch provide indexed retrieval as one jMunch layer.

The design is intentionally an installer and configuration manager. It is not an AI client, a
language server, an MCP proxy, an indexer, or a license server.

## Execution flow

```text
PowerShell/Bash launcher
  -> verify or bootstrap pinned uv
  -> run locked Python installer
     -> load and validate manifests
     -> detect supported clients
     -> build a non-secret plan
     -> display licenses and planned statuses
     -> require user declaration/confirmation
     -> snapshot owned paths
     -> install pinned tools and merge configuration
     -> report per-client, per-layer results and backup ID
```

`--dry-run` stops after planning. `--verify` reads configuration and probes only the selected
components. `--restore` uses a prior backup operation and performs no installation.

## Layer boundaries

### Layer 1: RTK

RTK rewrites supported shell commands so their output is compacted before an AI model consumes
it. The installer uses RTK's native integration target where appropriate. For Qwen Code, Kiro,
and the current Kilo CLI it writes delimited routing guidance. RTK init also creates
instruction-based integrations for Codex, Kimi, and Antigravity; these are `GUIDANCE ONLY`.

RTK configuration is either user-scoped or project-scoped according to the upstream integration.
The installer invokes RTK with telemetry disabled during setup.

### Layer 2: native/editor LSP

Language Server Protocol (LSP) lets tools ask language-aware questions such as “where is this
defined?”, “what references this symbol?”, and “what diagnostics apply here?”. A language server
process alone is not enough: the AI client must expose an agent-facing interface that can call it.

For that reason, unsupported client pairs are shown as **UNAVAILABLE FROM CLIENT** and receive no
standalone server configuration. That status describes an upstream client capability, not an
installer failure. Visual Studio Code is different: the editor already manages its language
extensions, so this installer reports Layer 2 as editor-managed and writes nothing for it.

Only the TypeScript/JavaScript, Python, Rust, and Go packs in `config/languages.json` are supported.
The planner intersects requested packs with each client's verified capability before an install
command is permitted.

### Layer 3: jMunch

Layer 3 always treats these three MCP servers as one functional layer:

- jCodeMunch retrieves source-code structure and stores its own data in `.code-index`.
- jDocMunch retrieves documentation and structured text and stores its own data in `.doc-index`.
- jDataMunch retrieves tabular datasets and stores its own data in `.data-index`.

Those directories are backing stores, not separate layers. The installer registers pinned MCP
server commands; it does not scan, upload, or pre-index project content.

Each component has separate non-commercial/commercial license terms. Planning is allowed without
a declaration, but applying Layer 3 is not.

## Manifests

The installer keeps volatile integration facts out of control flow:

- `config/bootstrap.json` pins downloadable launcher assets and SHA-256 checksums.
- `config/versions.json` pins tool/package versions and upstream sources.
- `config/clients.json` defines detection, integration scope, owned paths, config formats, and
  primary documentation sources.
- `config/languages.json` defines language packs and exact install commands.
- `config/licenses.json` records project, bundled, runtime, and client license/terms references.

Every manifest is validated before detection or mutation. Updating a version requires updating
the corresponding checksum, attribution, tests, and verification evidence where applicable.

## Configuration adapters

Client files are edited through format-specific adapters:

- JSON is parsed and merged structurally.
- JSONC is parsed while preserving unrelated comments and entries.
- TOML is updated structurally through TOMLKit.

The installer owns only the keys and files declared by its manifests. Existing unrelated values
are preserved. Absolute commands are used when a client requires them; otherwise MCP commands use
the isolated, pinned `uvx --from package==version` form.

Configuration backups can include credentials already present in client files. They stay in
private local state and are never logged or uploaded. Prompts and index contents are not collected.

## Backup and restore

An operation snapshots every owned path before the first change. The operation manifest records
whether each path originally existed and the hash written by the installer. Newly created files
and isolated directories are tracked too.

Restore is conservative:

- an original file is restored only if the current file still matches the installer-written hash;
- a newly created file or directory is removed only if it is unchanged;
- a changed path causes restore to stop with an actionable refusal instead of overwriting later
  user work.

Backups are local, per-user state. An operation ID is printed after successful apply and whenever
a failed apply progressed far enough to create a backup.

## Supply-chain controls

- The launchers pin uv and validate downloaded archives by SHA-256.
- RTK release assets are pinned and checksum-verified before extraction.
- Python dependencies are locked in `uv.lock` and invoked with `--frozen`.
- jMunch MCP commands pin exact package versions.
- LSP package-manager commands pin exact versions where the ecosystem permits it.
- Archive extraction rejects traversal and unsafe members.
- CI actions are pinned to full commit SHAs.

`--latest` is an explicit opt-out from the tested tool/package pins. In that mode, RTK is installed
to the managed target only after the official GitHub release API supplies a SHA-256 digest
for the exact asset. Language-server and jMunch package requests omit their version pins and use
the standard registry resolver. The plan labels these components untested and links the upstream
source; license declarations still apply.

Checksums establish artifact identity, not the trustworthiness of upstream software. Users remain
responsible for reviewing each third party's license, terms, and security posture.

## Verification limits

The result model distinguishes configuration checks from process-level MCP/LSP probes. A client
being present on `PATH` proves detection only. A valid config proves structure only. Neither is a
claim that an AI vendor account, subscription, remote model, or API entitlement works.

The installer never launches an AI CLI as an agent and never sends prompts to a model during
installation or verification.

Detection can invoke a client's non-agent `--version` command. Claude LSP setup invokes its
plugin-install administrative command. Tests use injected detections and runners and do not
launch AI clients. Package/runtime downloads can occur during launcher bootstrap and MCP probes.
