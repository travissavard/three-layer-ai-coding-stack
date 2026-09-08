"""Real, opt-in jMunch fixture checks shared by the live installer harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from three_layer_installer.adapters import adapter_for
from three_layer_installer.config_edit import read_config
from three_layer_installer.manifests import ManifestSet
from three_layer_installer.models import ClientId
from three_layer_installer.paths import PathContext
from three_layer_installer.verification import ProcessJsonRpcTransport

PRODUCTS = ("jcodemunch", "jdocmunch", "jdatamunch")


def decode_tool_result(response: Any) -> Any:
    assert isinstance(response, dict) and response.get("isError") is not True, (
        f"MCP tool failed: {response}"
    )
    texts = [item["text"] for item in response.get("content", []) if item.get("type") == "text"]
    assert len(texts) == 1, "expected one JSON tool result"
    value = json.loads(texts[0])
    assert not (
        isinstance(value, dict) and (value.get("error") or value.get("success") is False)
    ), f"jMunch action failed: {value}"
    result = value.get("result", value) if isinstance(value, dict) else value
    assert not (
        isinstance(result, dict) and (result.get("error") or result.get("success") is False)
    ), f"jMunch action failed: {result}"
    return result


def path_snapshot(path: Path) -> dict[str, str] | None:
    """Independent content baseline, including directory and symlink structure."""
    if not path.exists() and not path.is_symlink():
        return None
    paths = [path, *path.rglob("*")] if path.is_dir() and not path.is_symlink() else [path]
    result = {}
    for item in paths:
        name = str(item.relative_to(path))
        if item.is_symlink():
            result[name] = "link:" + str(item.readlink())
        elif item.is_dir():
            result[name] = "directory"
        else:
            result[name] = hashlib.sha256(item.read_bytes()).hexdigest()
    return result


def create_fixtures(root: Path) -> Path:
    fixtures = root / "jmunch-fixtures"
    (fixtures / "code").mkdir(parents=True)
    (fixtures / "docs").mkdir()
    (fixtures / "code/sample.py").write_text(
        'def cobalt_total(value: int) -> int:\n    """Return the fixture total."""\n'
        "    return value + 314\n",
        encoding="utf-8",
    )
    (fixtures / "docs/guide.md").write_text(
        "# Cobalt procedure\n\nThe cobalt launch phrase is violet-lantern-314.\n",
        encoding="utf-8",
    )
    (fixtures / "data.csv").write_text("name,total\ncobalt,314\namber,27\n", encoding="utf-8")
    return fixtures


def managed_prefixes(context: PathContext) -> list[Path]:
    return [context.state_root / "tools/jmunch" / product for product in PRODUCTS]


def verify_saved_entries(
    manifests: ManifestSet,
    context: PathContext,
    project: Path,
    fixtures: Path,
    *,
    fresh: bool,
    evidence: dict[str, Any],
) -> None:
    launches: dict[str, tuple[str, list[str], dict[str, str], list[str]]] = {}
    checked = []
    for client in ClientId:
        adapter = adapter_for(client, manifests, context, project=project)
        definition = adapter.definition["mcp"]
        assert isinstance(definition, dict)
        text = adapter.mcp_target.read_text(encoding="utf-8-sig")
        document = read_config(text, definition["format"])
        assert document.get("fixturePreserved") is True, (
            f"{client.value}: unrelated fixture setting was lost during installation"
        )
        if definition["format"] == "toml":
            assert "# preserved fixture" in text, (
                f"{client.value}: unrelated fixture comment was lost during installation"
            )
        saved = document.get(definition["root_key"], {})
        assert isinstance(saved, dict), f"{client.value}: missing MCP configuration root"
        for product in PRODUCTS:
            entry = saved.get(product)
            assert isinstance(entry, dict), f"{client.value}: missing {product} entry"
            assert entry.get("enabled") is not False and entry.get("disabled") is not True
            command = entry["command"]
            argv = list(command) if isinstance(command, list) else [command, *entry.get("args", [])]
            assert argv and all(isinstance(arg, str) and arg for arg in argv)
            environment = entry.get("environment", entry.get("env", {}))
            assert isinstance(environment, dict)
            assert all(environment.get(f"{name.upper()}_SHARE_SAVINGS") == "0" for name in PRODUCTS)
            assert all(isinstance(value, str) for value in environment.values())
            version = manifests.versions["tools"][product]
            if client is ClientId.CODEX:
                assert len(argv) == 1 and Path(argv[0]).is_file(), "managed MCP executable absent"
                assert Path(argv[0]).is_relative_to(context.state_root / "tools/jmunch" / product)
            else:
                assert argv[1:] == [
                    "--from",
                    f"{version['package']}=={version['version']}",
                    version["executable"],
                ]
            signature = json.dumps([product, argv, environment], sort_keys=True)
            if signature not in launches:
                launches[signature] = (product, argv, environment, [])
            launches[signature][3].append(client.value)
        checked.append(client.value)
    evidence["config_clients"] = checked
    evidence["launches"] = []
    seen = set()
    for product, argv, environment, clients in launches.values():
        item: dict[str, Any] = {"product": product, "clients": clients, "argv": argv, "calls": []}
        evidence["launches"].append(item)
        verify_entry(
            product,
            argv,
            environment,
            fixtures,
            manifests.versions["tools"][product]["version"],
            fresh=fresh and product not in seen,
            evidence=item,
        )
        seen.add(product)
    assert seen == set(PRODUCTS), "required product launches omitted"
    assert len(launches) == 6, "expected managed and uvx launch forms for all three products"


def verify_entry(
    product: str,
    argv: list[str],
    environment: dict[str, str],
    fixtures: Path,
    version: str,
    *,
    fresh: bool,
    evidence: dict[str, Any],
) -> None:
    rpc = ProcessJsonRpcTransport(argv, framing="line", timeout=180, environment=environment)

    def call(name: str, arguments: dict[str, Any]) -> Any:
        response = rpc.request("tools/call", {"name": name, "arguments": arguments})
        evidence["calls"].append({"name": name, "arguments": arguments, "response": response})
        return decode_tool_result(response)

    def code_call(
        action: str, arguments: dict[str, Any] | None = None, *, change: bool = False
    ) -> Any:
        return call(
            "order", {"action": action, "args": arguments or {}, "allow_state_change": change}
        )

    try:
        initialized = rpc.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "three-layer-live-verification", "version": "1"},
            },
        )
        assert initialized["serverInfo"]["name"] == product + "-mcp"
        assert initialized["serverInfo"]["version"] == version
        evidence["server"] = initialized["serverInfo"]
        rpc.notify("notifications/initialized", {})
        inventory = rpc.request("tools/list", {})
        assert inventory.get("tools"), "server exposed no tools"
        evidence["tools"] = [item["name"] for item in inventory["tools"]]
        if product == "jcodemunch":
            before = code_call("list_repos")
            if fresh:
                assert before["repos"] == [], "source index was not fresh"
            indexed = code_call(
                "index_folder",
                {
                    "path": str(fixtures / "code"),
                    "use_ai_summaries": False,
                },
                change=True,
            )
            repo = indexed["repo"]
            matches = code_call("search_symbols", {"repo": repo, "query": "cobalt_total"})
            assert matches["results"], "source search missed the fixture function"
            symbol_id = matches["results"][0]["id"]
            source = code_call("get_symbol_source", {"repo": repo, "symbol_id": symbol_id})
            assert "return value + 314" in json.dumps(source), (
                "retrieved source did not match fixture"
            )
        elif product == "jdocmunch":
            before = call("doc_list_repos", {})
            if fresh:
                assert before["repos"] == [], "documentation index was not fresh"
            indexed = call(
                "index_local",
                {
                    "path": str(fixtures / "docs"),
                    "name": "cobalt-docs",
                    "use_ai_summaries": False,
                    "use_embeddings": False,
                },
            )
            repo = indexed["repo"]
            matches = call("search_sections", {"repo": repo, "query": "cobalt"})
            assert matches["results"], "documentation search missed the fixture section"
            section = call("get_section", {"repo": repo, "section_id": matches["results"][0]["id"]})
            assert "violet-lantern-314" in json.dumps(section), (
                "retrieved document did not match fixture"
            )
        elif product == "jdatamunch":
            before = call("list_datasets", {})
            if fresh:
                assert before == [], "data index was not fresh"
            call("index_local", {"path": str(fixtures / "data.csv"), "name": "cobalt-data"})
            rows = call(
                "get_rows",
                {
                    "dataset": "cobalt-data",
                    "columns": ["name", "total"],
                    "filters": [{"column": "name", "op": "eq", "value": "cobalt"}],
                },
            )
            assert rows["total_matching"] == 1 and len(rows["rows"]) == 1
            assert {key: rows["rows"][0][key] for key in ("name", "total")} == {
                "name": "cobalt",
                "total": 314,
            }, "filtered data did not match fixture"
            absent = call(
                "get_rows",
                {
                    "dataset": "cobalt-data",
                    "filters": [{"column": "name", "op": "eq", "value": "absent"}],
                },
            )
            assert absent["rows"] == [] and absent["total_matching"] == 0
        else:
            raise AssertionError(f"unexpected jMunch product: {product}")
        evidence["passed"] = True
    finally:
        rpc.close()
