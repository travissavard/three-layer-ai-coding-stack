"""Opt-in network integration tests; no AI clients, model calls, or jMunch use.

Runs the real launcher/RTK installer and real language-server install commands.
Seeded client configuration tests adapter setup, NOT real client consumption.
All mutable tool/config/cache paths live in a newly created disposable profile.
The profile is retained for inspection; only the installer's restore removes files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLIENT_COMMANDS = (
    "claude",
    "codex",
    "copilot",
    "gemini",
    "qwen",
    "kimi",
    "kilo",
    "kiro-cli",
    "kiro",
    "antigravity",
    "code",
)


def isolated_environment(root: Path, *, native_home: Path | None = None) -> dict[str, str]:
    """Allowlist environment, not a copy of the user's credentials or AI config."""
    env = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
        if key in os.environ
    }
    task_home = native_home or root / "home"
    for relative in ("home", "tmp", "bin", "npm", "go/bin", "cache"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    paths = [str(root / "bin"), str(root / "npm"), str(root / "npm/bin"), str(root / "go/bin")]
    for tool in ("node", "npm", "git", "go"):
        found = shutil.which(tool)
        if found:
            paths.append(str(Path(found).parent))
    if os.name == "nt":
        paths.extend(
            [str(Path(os.environ["SYSTEMROOT"]) / "System32"), str(Path(os.environ["SYSTEMROOT"]))]
        )
    else:
        paths.extend(["/usr/bin", "/bin", "/usr/sbin", "/sbin"])
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Install uv as a prerequisite for the live test harness")
    for name in ("uv.exe", "uvx.exe") if os.name == "nt" else ("uv", "uvx"):
        source = Path(uv).parent / name
        if source.is_file():
            shutil.copy2(source, root / "bin" / name)
    env.update(
        {
            "PATH": os.pathsep.join(dict.fromkeys(paths)),
            "HOME": str(task_home),
            "USERPROFILE": str(task_home),
            "APPDATA": str(task_home / "AppData/Roaming"),
            "LOCALAPPDATA": str(task_home / "AppData/Local"),
            "XDG_CONFIG_HOME": str(task_home / ".config"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "XDG_DATA_HOME": str(task_home / ".local/share"),
            "XDG_STATE_HOME": str(task_home / ".local/state"),
            "TEMP": str(root / "tmp"),
            "TMP": str(root / "tmp"),
            "TMPDIR": str(root / "tmp"),
            "UV_NO_CONFIG": "true",
            "UV_CACHE_DIR": str(root / "cache/uv"),
            "UV_PYTHON": sys.executable,
            "UV_PYTHON_INSTALL_DIR": str(root / "python"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "NO_COLOR": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "npm_config_prefix": str(root / "npm"),
            "npm_config_cache": str(root / "cache/npm"),
            "npm_config_userconfig": str(root / "npmrc"),
            "npm_config_globalconfig": str(root / "npm-globalrc"),
            "npm_config_registry": "https://registry.npmjs.org/",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "GOPATH": str(root / "go"),
            "GOCACHE": str(root / "cache/go"),
            "GOTOOLCHAIN": "auto",
            "RTK_TELEMETRY_DISABLED": "1",
            "GOTELEMETRY": "off",
        }
    )
    if native_home:
        env["THREE_LAYER_TEST_NATIVE_HOME"] = str(native_home)
    for name in CLIENT_COMMANDS:
        if shutil.which(name, path=env["PATH"]):
            raise RuntimeError(f"Isolation refused: {name} is on the test PATH")
    if shutil.which("rtk", path=env["PATH"]):
        raise RuntimeError("Isolation refused: existing RTK is on the test PATH")
    return env


def worker(root: Path, launcher: str, languages: list[str], report_path: Path) -> int:
    from three_layer_installer.adapters import adapter_for
    from three_layer_installer.manifests import load_manifests
    from three_layer_installer.models import ClientId
    from three_layer_installer.paths import PathContext
    from three_layer_installer.verification import ProcessJsonRpcTransport

    context = PathContext.current()
    native_home = os.environ.get("THREE_LAYER_TEST_NATIVE_HOME")
    expected_home = Path(native_home) if native_home else root / "home"
    assert context.home.resolve() == expected_home.resolve()
    manifest = load_manifests()
    project = root / "project"
    project.mkdir()
    report: dict = {
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "scope": "real-tool integration only",
        "client_consumption": "UNPROVEN: no AI client is launched",
        "jmunch": "UNPROVEN: license basis not declared; not installed or executed",
        "isolation": "disposable CI Windows user" if native_home else "temporary home and PATH",
        "commands": [],
        "checks": [],
    }

    class EvidenceTransport(ProcessJsonRpcTransport):
        def _read_sync(self):
            response = super()._read_sync()
            if "error" in response:
                report.setdefault("protocol_errors", []).append(response)
            if response.get("method") in {"window/showMessage", "window/logMessage"}:
                report.setdefault("server_messages", []).append(response)
            return response

    def save() -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = json.dumps(report, indent=2)
        # Only controlled fixtures/allowlisted env are used; redact machine-local paths too.
        for value, replacement in (
            (str(root), "<TEST_ROOT>"),
            (root.as_uri(), "<TEST_ROOT_URI>"),
            (REPO.as_uri(), "<REPO_URI>"),
            (str(REPO), "<REPO>"),
            (str(expected_home), "<TEST_HOME>"),
            (str(Path(sys.executable).parent), "<PYTHON_BIN>"),
        ):
            rendered = rendered.replace(json.dumps(value)[1:-1], replacement)
        report_path.write_text(rendered + "\n", encoding="utf-8")

    def check(name: str, action) -> None:
        started = time.monotonic()
        try:
            detail = action()
            result = {"name": name, "status": "PASS", "detail": detail}
        except Exception as exc:
            result = {"name": name, "status": "FAIL", "detail": str(exc)}
        result["seconds"] = round(time.monotonic() - started, 2)
        report["checks"].append(result)
        print(f"{name}: {result['status']} - {result['detail']}", flush=True)
        save()

    def run(argv: list[str], *, expected: int = 0, data: str | None = None) -> str:
        argv = [shutil.which(argv[0]) or argv[0], *argv[1:]]
        started = time.monotonic()
        completed = subprocess.run(
            argv,
            cwd=project,
            input=data,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        report["commands"].append(
            {
                "argv": argv,
                "exit_code": completed.returncode,
                "seconds": round(time.monotonic() - started, 2),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        save()
        if completed.returncode != expected:
            raise AssertionError(
                f"{Path(argv[0]).name}: exit {completed.returncode}, "
                f"expected {expected}; see command log"
            )
        return completed.stdout

    prefix = (
        [launcher, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REPO / "install.ps1")]
        if os.name == "nt"
        else [launcher, str(REPO / "install.sh")]
    )
    args = [
        "--all",
        "--yes",
        "--jmunch-use",
        "skip",
        "--languages",
        "none",
        "--project",
        str(project),
    ]
    # Existing config is a real supported detection route. These are explicit fixtures,
    # not stand-ins claimed as live clients. Versions/LSP client setup remain unproven.
    for client in ClientId:
        target = adapter_for(client, manifest, context).mcp_target
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(
                "# preserved fixture\n"
                if target.suffix == ".toml"
                else '{"fixturePreserved": true}\n',
                encoding="utf-8",
            )
    sentinel = project / "untouched.txt"
    sentinel.write_text("must survive install and restore\n", encoding="utf-8")
    sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    install_ids: list[str] = []
    config_roots = [
        context.home / name
        for name in (
            ".claude",
            ".codex",
            ".copilot",
            ".gemini",
            ".qwen",
            ".kimi",
            ".kiro",
            ".config/kilo",
        )
    ]
    config_roots.append(project)

    def config_snapshot() -> dict[str, str]:
        return {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in config_roots
            if folder.is_dir()
            for path in folder.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(folder).parts
        }

    baseline_configs = config_snapshot()

    def apply() -> str:
        stdout = run([*prefix, *args])
        ids = re.findall(r"Backup ID: ([\w-]+)", stdout)
        assert len(ids) == 1, "real installation did not produce exactly one backup ID"
        install_ids.append(ids[0])
        return ids[0]

    check("fresh RTK install + all config-detected adapters", apply)
    rtk = context.state_root / "bin" / ("rtk.exe" if os.name == "nt" else "rtk")

    def require_rtk_binary() -> str:
        assert rtk.is_file(), "fresh installation did not produce the managed RTK binary"
        return "managed RTK executable exists"

    check("required RTK binary", require_rtk_binary)
    if rtk.exists():

        def rtk_queries() -> str:
            version = run([str(rtk), "--version"]).strip()
            assert "0.48.0" in version, version
            run(["git", "init", "--quiet"])
            status = run([str(rtk), "git", "status"])
            assert "untouched.txt" in status, "RTK dropped the known fixture change"
            gain = run([str(rtk), "gain"])
            assert gain.strip(), "RTK returned no gain output"
            return version + "; git status preserved fixture filename; gain executed"

        check("RTK actual commands", rtk_queries)
        check("reinstall", apply)
    if len(install_ids) == 2:

        def conflict_restore() -> str:
            target = context.home / ".qwen/QWEN.md"
            original = target.read_bytes()
            target.write_bytes(original + b"\nfixture user edit\n")
            try:
                before = config_snapshot()
                run([*prefix, "--restore", install_ids[-1]], expected=5)
                assert config_snapshot() == before, "refused restore changed client files"
            finally:
                target.write_bytes(original)
            return "restore refused edited config; every client file remained unchanged"

        check("restore conflict protection", conflict_restore)
        for operation_id in reversed(install_ids):

            def restore(operation_id=operation_id) -> str:
                record_path = context.state_root / "operations" / operation_id / "manifest.json"
                records = json.loads(record_path.read_text(encoding="utf-8"))["files"]
                assert records, "restore test has no owned files"
                for record in records:
                    target = Path(record["path"]).resolve()
                    assert target.is_relative_to(root.resolve()) or (
                        native_home and target.is_relative_to(expected_home.resolve())
                    ), "restore target escaped the disposable environment"
                run([*prefix, "--restore", operation_id])
                for record in records:
                    target = Path(record["path"])
                    if record["existed"]:
                        assert target.is_file(), f"missing restored fixture: {target}"
                        assert (
                            hashlib.sha256(target.read_bytes()).hexdigest()
                            == record["before_sha256"]
                        ), f"restore hash mismatch: {target}"
                    else:
                        assert not target.exists(), f"new owned file survived restore: {target}"
                assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_hash
                return f"{len(records)} owned file states match baseline; unrelated file preserved"

            check("restore " + operation_id, restore)

        def complete_config_restore() -> str:
            after = config_snapshot()
            extra = sorted(set(after) - set(baseline_configs))
            assert after == baseline_configs, f"client config tree differs; extra files: {extra}"
            return "entire client config trees and project fixtures match baseline"

        check("complete config tree restore", complete_config_restore)

    for language in languages:
        definition = manifest.languages["languages"][language]

        def language_test(language=language, definition=definition) -> str:
            command = definition["command"]
            assert not shutil.which(command[0]), "server already present; not a fresh install"
            run(definition["installer"])
            assert shutil.which(command[0]), "installer did not put language server on test PATH"
            folder = project / language
            folder.mkdir()
            if language == "typescript":
                name, content, line, char = (
                    "sample.ts",
                    "function doubled(value: number): number {\n"
                    "  return value * 2;\n}\nconst result = doubled(21);\n",
                    3,
                    17,
                )
                (folder / "tsconfig.json").write_text('{"include":["*.ts"]}', encoding="utf-8")
            elif language == "python":
                name, content, line, char = (
                    "sample.py",
                    "def doubled(value: int) -> int:\n"
                    "    return value * 2\n\nresult = doubled(21)\n",
                    3,
                    10,
                )
            elif language == "go":
                name, content, line, char = (
                    "main.go",
                    "package main\n"
                    "func doubled(value int) int { return value * 2 }\n"
                    "func main() { _ = doubled(21) }\n",
                    2,
                    20,
                )
                (folder / "go.mod").write_text(
                    "module example.test/live\n\ngo 1.24\n", encoding="utf-8"
                )
            else:
                raise ValueError("This harness currently exercises TypeScript, Python, and Go")
            document = folder / name
            document.write_text(content, encoding="utf-8")
            rpc = EvidenceTransport(command, framing="content-length", timeout=60)
            try:
                initialized = rpc.request(
                    "initialize",
                    {
                        "processId": None,
                        "rootUri": folder.as_uri(),
                        "workspaceFolders": [{"uri": folder.as_uri(), "name": language}],
                        "capabilities": {},
                    },
                )
                assert initialized.get("capabilities"), "missing LSP capabilities"
                rpc.notify("initialized", {})
                rpc.notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": document.as_uri(),
                            "languageId": language,
                            "version": 1,
                            "text": content,
                        }
                    },
                )
                params = {
                    "textDocument": {"uri": document.as_uri()},
                    "position": {"line": line, "character": char},
                }
                symbols = rpc.request(
                    "textDocument/documentSymbol", {"textDocument": params["textDocument"]}
                )
                assert "doubled" in json.dumps(symbols), "known symbol absent from LSP result"
                locations = rpc.request("textDocument/definition", params)
                assert locations, "empty definition for known function call"
                assert name in json.dumps(locations), "definition points outside fixture"
                refs = rpc.request(
                    "textDocument/references", {**params, "context": {"includeDeclaration": True}}
                )
                assert isinstance(refs, list) and len(refs) >= 2, "call references absent"
                hover = rpc.request("textDocument/hover", params)
                assert "doubled" in json.dumps(hover), "hover missing function signature"
                report.setdefault("lsp_results", {})[language] = {
                    "symbols": symbols,
                    "definition": locations,
                    "references": refs,
                    "hover": hover,
                }
                rpc.request("shutdown", {})
                rpc.notify("exit", {})
            finally:
                rpc.close()
            return "fresh package + nonempty symbols, definition, references, and hover"

        check(language + " language server", language_test)

    report["passed"] = all(item["status"] == "PASS" for item in report["checks"])
    report["full_end_to_end"] = False
    save()
    return 0 if report["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default="typescript,python")
    parser.add_argument("--report", type=Path, default=REPO / ".e2e-results/live-tools.json")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--launcher", help=argparse.SUPPRESS)
    parser.add_argument(
        "--ci-native-home",
        action="store_true",
        help="Windows only: requires an ephemeral GitHub Actions runner",
    )
    args = parser.parse_args()
    languages = args.languages.split(",") if args.languages else []
    if set(languages) - {"typescript", "python", "go"}:
        parser.error("supported test fixtures: typescript,python,go")
    if args.worker:
        return worker(args.worker, args.launcher, languages, args.report)
    native_home = None
    if os.name == "nt":
        if not args.ci_native_home or os.environ.get("GITHUB_ACTIONS") != "true":
            parser.error(
                "RTK ignores USERPROFILE on Windows. Run this on an ephemeral "
                "GitHub Actions Windows runner with --ci-native-home, not a user's PC."
            )
        native_home = Path.home()
    elif args.ci_native_home:
        parser.error("--ci-native-home is Windows-only")
    launcher = shutil.which("pwsh" if os.name == "nt" else "bash")
    if not launcher:
        raise RuntimeError("PowerShell 7 or Bash is required for real launcher verification")
    root = Path(tempfile.mkdtemp(prefix="three-layer-live-"))
    print(f"Disposable profile retained at {root}", flush=True)
    env = isolated_environment(root, native_home=native_home)
    return subprocess.call(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            str(root),
            "--launcher",
            launcher,
            "--languages",
            args.languages,
            "--report",
            str(args.report.resolve()),
        ],
        env=env,
        cwd=REPO,
    )


if __name__ == "__main__":
    raise SystemExit(main())
