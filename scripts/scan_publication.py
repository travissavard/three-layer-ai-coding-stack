"""Scan repository files and reachable Git history without printing matched values."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "personal Windows home": rb"[A-Za-z]:[\\/]Users[\\/][^\\/\s]+",
    "AWS access key": rb"(?:AKIA|ASIA)[0-9A-Z]{16}",
    "GitHub token": rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})",
    "API secret": rb"sk-[A-Za-z0-9_-]{20,}",
    "private key": rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "credential-bearing URL": rb"https?://[^\s/:]+:[^\s/@]+@",
}


def git(*args: str, payload: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, input=payload)


def main() -> None:
    findings: set[tuple[str, str]] = set()

    def scan(label: str, data: bytes) -> None:
        for name, pattern in PATTERNS.items():
            if re.search(pattern, data):
                findings.add((label, name))

    files = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
    for name in set(files) - {b""}:
        path = ROOT / name.decode("utf-8")
        if path.is_file():
            scan(str(path.relative_to(ROOT)), path.read_bytes())

    objects = git("rev-list", "--objects", "--all").splitlines()
    hashes = [line.split(b" ", 1)[0] for line in objects]
    payload = git("cat-file", "--batch", payload=b"\n".join(hashes) + b"\n")
    offset = 0
    blobs = 0
    while offset < len(payload):
        end = payload.index(b"\n", offset)
        object_id, kind, raw_size = payload[offset:end].split()
        size = int(raw_size)
        data = payload[end + 1 : end + 1 + size]
        if kind in {b"blob", b"commit", b"tag"}:
            scan("history:" + object_id.decode()[:12], data)
            blobs += 1
        offset = end + size + 2
    if findings:
        for label, rule in sorted(findings):
            print(f"{label}: {rule} (value redacted)")
        raise SystemExit(1)
    print(f"Publication scan passed: {len(set(files) - {b''})} files, {blobs} history objects")


if __name__ == "__main__":
    main()
