# Security policy

## Supported versions

Security fixes are applied to the latest release and the default branch. Older installer snapshots
may continue to reference pinned upstream assets that are no longer current.

## Reporting a vulnerability

Do not publish exploit details, credentials, private configuration, or repository contents in a
public issue.

Use GitHub's **Report a vulnerability** flow for this repository when it is available. If that
button is unavailable, open a minimal public issue asking the maintainers to establish a private
contact channel. Include no sensitive details in that issue.

In a private report, include:

- the affected installer version or commit;
- operating system and architecture;
- the smallest safe reproduction;
- expected and observed behavior;
- impact and any known workarounds; and
- whether public disclosure has already occurred.

Reports are assessed against the actual installer boundary. Vulnerabilities in RTK, uv, jMunch,
language servers, or AI clients may need coordinated reporting to their respective publishers.

## Security boundaries

The installer must not:

- request or transmit API keys, account credentials, prompts, source files, or index contents;
- launch an AI CLI to send prompts or act as an autonomous agent;
- bypass checksum, license-declaration, confirmation, or hash-guarded restore controls;
- overwrite unrelated client configuration; or
- report estimated token savings as billing evidence.

Downloaded bootstrap and RTK artifacts are pinned and checksum-verified. Python dependencies are
locked. These controls verify artifact identity; they do not replace review of upstream software.
Existing credentials can be present in private local configuration backups. Never publish backups.
