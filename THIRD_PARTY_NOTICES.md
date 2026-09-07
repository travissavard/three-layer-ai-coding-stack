# Third-party notices

Verified 2026-09-06. This inventory describes software downloaded, installed, invoked, or
configured by this project. Third-party software is not relicensed under this repository's MIT
license. Its upstream license and product terms continue to control.

## jMunch commercial-use notice

Layer 3 contains three separate works by J. Gravelle. Each is free only for use that qualifies
under its non-commercial grant. Use within a for-profit organization, internal tooling that
supports revenue, consulting, SaaS, or another commercial workflow requires the applicable paid
commercial license from the publisher. The installer's `commercial-licensed` declaration means only that the
user says they already have the required rights; it does not purchase, validate, or grant them.

| Component | Installed version | Published license | Commercial licensing |
|---|---:|---|---|
| jCodeMunch-MCP | 1.108.317 | [Dual-Use License 1.1 (`LicenseRef-jCodeMunch-Dual-Use-1`)](https://github.com/jgravelle/jcodemunch-mcp/blob/main/LICENSE) | [Publisher options](https://jcodemunch.com/descriptions.php) |
| jDocMunch-MCP | 1.139.1 | [jDocMunch-MCP Dual-Use License (`LicenseRef-jDocMunch-Dual-Use`)](https://github.com/jgravelle/jdocmunch-mcp/blob/master/LICENSE) | [Publisher options](https://jcodemunch.com/descriptions.php) |
| jDataMunch-MCP | 1.31.13 | [jDataMunch-MCP Dual-Use License (`LicenseRef-jDataMunch-Dual-Use`)](https://github.com/jgravelle/jdatamunch-mcp/blob/master/LICENSE) | [Publisher options](https://jcodemunch.com/descriptions.php) |

Copyright notice for all three: Copyright (c) 2024-2026 J. Gravelle. All rights reserved.
Always check the linked controlling terms before use; license terms and commercial offerings can
change independently of this repository.

The publisher lists Builder, Studio, and Platform commercial tiers for each jMunch product.
See the [licensing destination linked by the licenses](https://j.gravelle.us/jCodeMunch/descriptions.php)
for current scope and pricing. No jMunch source code or binaries are redistributed here.

The optional `--latest` mode requests current registry releases instead of the versions listed in
this inventory. Those releases are intentionally untested by this repository and may have changed
terms. The installer still displays all three controlling jMunch license links and requires the
same explicit use declaration before configuration.

## Downloaded and runtime components

| Component | Relationship | License / terms |
|---|---|---|
| RTK 0.48.0 | Downloaded from its GitHub release when absent | [Apache-2.0](https://github.com/rtk-ai/rtk/blob/v0.48.0/LICENSE) |
| uv 0.12.10 | Checksum-verified bootstrap download when absent | [MIT OR Apache-2.0](https://github.com/astral-sh/uv/tree/main#license) |
| TOMLKit 0.15.1 | Python runtime dependency | [MIT](https://github.com/python-poetry/tomlkit/blob/master/LICENSE) |
| Python 3.10+ | Runtime, obtained by uv when needed | [PSF-2.0](https://docs.python.org/3/license.html) |
| TypeScript Language Server 6.0.0 | Optional language pack | [Apache-2.0 with MIT portions](https://github.com/typescript-language-server/typescript-language-server/blob/master/LICENSE) |
| TypeScript 6.0.3 | Optional language pack | [Apache-2.0](https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt) |
| Pyright 1.1.413 | Optional language pack | [MIT](https://github.com/microsoft/pyright/blob/main/LICENSE.txt) |
| gopls 0.23.0 | Optional language pack | [BSD-3-Clause](https://github.com/golang/tools/blob/master/LICENSE) |
| rust-analyzer | Optional active-rustup-toolchain component | [MIT OR Apache-2.0](https://github.com/rust-lang/rust-analyzer#license) |
| rustup | Existing prerequisite copied into the isolated Rust test environment | [MIT OR Apache-2.0](https://github.com/rust-lang/rustup#license) |
| Rust toolchain and rust-src | Downloaded into isolated directories by the optional live tests | [MIT OR Apache-2.0; bundled third-party notices also apply](https://github.com/rust-lang/rust#license) |

These packages are acquired from their documented upstream release page or standard package
registry. The repository does not vendor their source or binaries.

## Configured applications and services

The installer does not install or license an AI client. A client's open-source license does not
replace the account, API, subscription, enterprise-policy, marketplace, or service terms that may
apply to its use.

| Client | Code/product license or terms |
|---|---|
| Claude Code | [Anthropic commercial terms](https://www.anthropic.com/legal/commercial-terms) |
| Codex CLI | [Apache-2.0](https://github.com/openai/codex/blob/main/LICENSE) plus applicable OpenAI service terms |
| GitHub Copilot CLI | [GitHub additional product terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features) |
| Gemini CLI | [Apache-2.0](https://github.com/google-gemini/gemini-cli/blob/main/LICENSE) plus applicable Google service terms |
| Qwen Code | [Apache-2.0](https://github.com/QwenLM/qwen-code/blob/main/LICENSE) plus applicable service terms |
| Kimi CLI | [Apache-2.0](https://github.com/MoonshotAI/kimi-cli/blob/main/LICENSE) plus applicable service terms |
| Kilo Code | [MIT](https://github.com/Kilo-Org/kilocode/blob/main/LICENSE) plus applicable service terms |
| Kiro | [AWS service terms](https://aws.amazon.com/service-terms/) |
| Antigravity | [Google terms](https://policies.google.com/terms) |
| Visual Studio Code | [Microsoft product license](https://code.visualstudio.com/license); extensions and AI services have separate terms |

All product and project names are used only to identify compatibility. They remain trademarks of
their respective owners. This project is not endorsed by those owners.
