# Troubleshooting

Start with a dry-run. It validates manifests, detects clients, resolves scopes, and prints every
layer status without installing target tools or changing client configuration. The launcher may
still download its temporary uv/Python/dependency environment.

```bash
./install.sh --all --project /path/to/project --languages auto --dry-run
```

On Windows PowerShell, replace `./install.sh` with `.\install.ps1`.

## No supported AI clients were detected

Make sure the client executable is installed and available on `PATH` in the same terminal. For
example, `claude`, `codex`, or `copilot` must resolve as a command. An explicit `--client` selector
will show that client's skipped status when it is not detected; it does not install the AI client.

Restart the terminal after changing `PATH`.

## RTK is not on PATH

New RTK downloads go into the installer's managed `bin` directory. Add that directory to your
user PATH through your normal shell or Windows environment settings, then restart the client:

| Platform | Default managed bin |
| --- | --- |
| Windows | `%LOCALAPPDATA%\three-layer-ai-coding-stack\bin` |
| macOS | `~/Library/Application Support/three-layer-ai-coding-stack/bin` |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/three-layer-ai-coding-stack/bin` |

The exact path is printed by the installer. RTK native hooks need `rtk` on the client's PATH.
`--latest` uses this managed executable too; place its directory before any older RTK installation.

## A project integration was skipped

Kimi, Kilo, and Antigravity use project-scoped RTK integration. Qwen and Kiro use project files
for LSP. Supply the project root explicitly:

```bash
./install.sh --client kilo --project /path/to/project --languages auto --jmunch-use skip
```

The installer does not guess a project directory for project-scoped writes.

## Layer 2 says UNAVAILABLE FROM CLIENT

This is an expected capability status, not an installation error. LSP lets a tool obtain code
definitions, references, types, and diagnostics, but the AI client must expose an agent-facing LSP
interface. The affected AI CLI currently does not. That limitation comes from the client, not this
installer, and installing a language server alone cannot add the missing interface.

For Visual Studio Code, Layer 2 is editor-managed and intentionally skipped because installed
editor language extensions already provide LSP.

## An LSP runtime is missing

Each language pack needs its normal runtime/package manager:

| Pack | Required command |
| --- | --- |
| TypeScript/JavaScript | `npm` |
| Python (Pyright) | `npm` |
| Rust | Rust toolchain/rust-analyzer installation support |
| Go | `go` |

Install the runtime from its official distribution, reopen the terminal, and rerun the same plan.
The installer checks the prerequisite before invoking a package manager.

## jMunch declaration is required

Layer 3 cannot be applied until you declare a license basis. Review each component's terms in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), then use exactly one of:

```text
--jmunch-use noncommercial
--jmunch-use commercial-licensed
--jmunch-use skip
```

`--yes` deliberately fails without an explicit declaration. The installer cannot determine
whether a use is commercial and cannot purchase or verify a license for you.

## A configuration file cannot be parsed

The installer refuses to replace malformed JSON, JSONC, or TOML. Validate the file named in the
error, repair its syntax, and rerun. Existing unrelated keys and comments are preserved when the
file is valid.

Use `--dry-run` to confirm the intended client and scope before retrying.

## Installation failed after a backup was created

Keep the printed backup ID. The failure output includes the exact restore form:

```bash
./install.sh --restore OPERATION_ID
```

If the failed run made no changes, restore is harmless. If a path changed after the installer
wrote it, restore refuses to overwrite that newer work.

## Restore was refused

Restore is hash-guarded. A refusal means at least one installer-managed path no longer matches the
state written by that operation. Copy or commit your later edits, return the path to the
installer-written content if appropriate, and retry. The installer does not offer a force flag
because silently discarding later work would be unsafe.

## A checksum verification failed

Do not bypass the check. Delete only the temporary installer download if it remains, verify that a
proxy or security product is not rewriting downloads, and retry. If the pinned upstream release
was replaced or removed, open an issue with the platform, architecture, asset name, and expected
versus received checksum—but never include credentials or private configuration.

In `--latest` mode, RTK also fails closed when GitHub's official release metadata omits a valid
SHA-256 digest for the selected platform asset. Use the default pinned mode rather than bypassing
that identity check.

## Windows ARM64 and RTK

The pinned RTK release does not provide a Windows ARM64 artifact. The rest of the installer can
bootstrap on Windows ARM64, but Layer 1 cannot install a native RTK binary from that release. The
installer reports this instead of downloading an unverified substitute.

## Verify a configured stack

Use the same selection, project, languages, and jMunch declaration as installation:

```bash
./install.sh --client claude --verify --languages typescript --jmunch-use noncommercial
```

Verification confirms only the scope printed in its results. It does not authenticate to an AI
vendor, consume API credits, or send a prompt to a model.
