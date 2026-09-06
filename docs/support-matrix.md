# Supported client matrix

This matrix describes integrations verified against the linked upstream documentation on
2026-09-06. “Supported” means the installer has a tested configuration adapter for the documented
client interface; it does not imply endorsement by any client or tool vendor.

## Layer status

| Client selector | Client | RTK | Native/editor LSP | jMunch MCP |
| --- | --- | --- | --- | --- |
| `claude` | Claude Code | Native, user scope | Native: TypeScript/JavaScript, Python, Rust | User scope |
| `codex` | Codex CLI | Guidance via RTK init, user scope | **UNAVAILABLE FROM CLIENT** | User scope |
| `copilot` | GitHub Copilot CLI | Native, user scope | Native: TypeScript/JavaScript, Python, Rust, Go | User scope |
| `gemini` | Gemini CLI | Native, user scope | **UNAVAILABLE FROM CLIENT** | User scope |
| `qwen` | Qwen Code | Guidance, user scope | Experimental: project scope; TypeScript/JavaScript, Python, Rust, Go | User scope |
| `kimi` | Kimi CLI | Guidance via RTK init, project scope | **UNAVAILABLE FROM CLIENT** | User scope |
| `kilo` | Kilo Code | Guidance in AGENTS.md, project scope | Native: user/project scope; TypeScript/JavaScript, Python, Rust, Go | User or project scope |
| `kiro` | Kiro CLI/IDE | Guidance, user scope | Native: project scope; TypeScript/JavaScript, Python, Rust, Go | User or project scope |
| `antigravity` | Antigravity | Guidance via RTK init, project scope | **UNAVAILABLE FROM CLIENT** | User or project scope |
| `vscode` | Visual Studio Code | Native, user scope | Editor-managed; installer writes no standalone LSP config | User or project scope |

Layer 3 is a single layer containing jCodeMunch, jDocMunch, and jDataMunch. All three are configured
together unless `--jmunch-use skip` is selected.

## Why Layer 2 varies

LSP is a standard way to ask a language-aware service for definitions, references, symbols,
types, and diagnostics. The AI client must provide agent-facing LSP support before an installer
can connect those services safely.

**UNAVAILABLE FROM CLIENT** therefore means the upstream AI client does not currently expose a
supported interface. It does not mean the installer failed, and installing a language server by
itself cannot create that missing client interface. Visual Studio Code already handles LSP through
editor extensions, so it is reported separately as editor-managed.

## Integration sources

The canonical, machine-readable source links and configuration schemas are in
[`config/clients.json`](../config/clients.json). They point to primary vendor documentation for
each client:

- [Claude Code plugins/LSP](https://code.claude.com/docs/en/plugins-reference#lsp-servers) and
  [MCP](https://code.claude.com/docs/en/mcp)
- [Codex CLI features](https://developers.openai.com/codex/cli/features) and
  [MCP](https://developers.openai.com/codex/mcp)
- [GitHub Copilot CLI LSP](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/lsp-servers)
  and [MCP](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)
- [Gemini CLI tools](https://geminicli.com/docs/tools/) and
  [MCP](https://geminicli.com/docs/tools/mcp-server/)
- [Qwen Code LSP](https://qwenlm.github.io/qwen-code-docs/en/users/features/lsp/) and
  [MCP](https://qwenlm.github.io/qwen-code-docs/en/users/features/mcp/)
- [Kimi CLI MCP](https://moonshotai.github.io/kimi-cli/en/customization/mcp.html)
- [Kilo Code CLI](https://kilo.ai/docs/code-with-ai/platforms/cli) and
  [MCP](https://kilo.ai/docs/automate/mcp/using-in-kilo-code)
- [Kiro code intelligence](https://kiro.dev/docs/cli/code-intelligence/) and
  [MCP](https://kiro.dev/docs/mcp/configuration/)
- [Antigravity codelab](https://codelabs.developers.google.com/getting-started-google-antigravity)
- [Visual Studio Code languages](https://code.visualstudio.com/docs/languages/overview) and
  [MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)

RTK native-target claims are grounded in the pinned
[`v0.48.0` integration source](https://github.com/rtk-ai/rtk/blob/v0.48.0/src/hooks/init.rs).

## Selection behavior

- With no selector, clients found on `PATH` or through existing supported config files are selected.
- `--client NAME` explicitly selects one client and can be repeated.
- `--all` selects every supported detected client. Explicitly selected absent clients are skipped.
- Project-scoped integrations require `--project PATH`.
- Unsupported language/client pairs are reported as skipped and are never force-configured.

## Native LSP version gates

| Client | Minimum version | Primary source |
| --- | --- | --- |
| Claude Code | 2.0.74 | [Release](https://github.com/anthropics/claude-code/releases/tag/v2.0.74) |
| Copilot CLI | 0.0.405 | [Changelog](https://github.com/github/copilot-cli/blob/main/changelog.md#00405---2026-02-05) |
| Qwen Code | 0.9.0 | [Release](https://github.com/QwenLM/qwen-code/releases/tag/v0.9.0) |
| Kilo CLI | 1.0.0 | [CLI documentation](https://kilo.ai/docs/code-with-ai/platforms/cli) |
| Kiro CLI | 1.22.0 | [Release](https://kiro.dev/changelog/cli/1-22/) |

These are conservative supported floors. Unreadable versions fail closed for LSP. Qwen requires
the `--experimental-lsp` client flag. Kiro IDE language extensions remain editor-managed.
Kilo's project instructions use its documented [AGENTS.md support](https://kilo.ai/docs/customize/custom-instructions).
