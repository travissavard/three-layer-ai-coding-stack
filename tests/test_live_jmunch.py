"""Guard the live evidence checker against false passes; no network calls."""

import importlib.util
import json
from pathlib import Path

import pytest

from three_layer_installer.adapters import adapter_for
from three_layer_installer.manifests import load_manifests
from three_layer_installer.models import ClientId
from three_layer_installer.paths import PathContext, PlatformKind

SPEC = importlib.util.spec_from_file_location(
    "live_jmunch", Path(__file__).resolve().parents[1] / "scripts/live_jmunch.py"
)
assert SPEC is not None and SPEC.loader is not None
LIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LIVE)


@pytest.mark.parametrize("payload", [{"error": "index failed"}, {"success": False}])
def test_nested_action_errors_cannot_be_used_as_evidence(payload: dict[str, object]) -> None:
    with pytest.raises(AssertionError, match="action failed"):
        LIVE.decode_tool_result(
            {"content": [{"type": "text", "text": json.dumps({"result": payload})}]}
        )


def test_tool_error_flag_is_not_hidden_by_a_valid_result() -> None:
    with pytest.raises(AssertionError, match="MCP tool failed"):
        LIVE.decode_tool_result(
            {"isError": True, "content": [{"type": "text", "text": '{"rows": []}'}]}
        )


def test_real_result_envelopes_preserve_fixture_values() -> None:
    assert LIVE.decode_tool_result(
        {"content": [{"type": "text", "text": '{"result":{"total":314}}'}]}
    ) == {"total": 314}
    assert LIVE.decode_tool_result(
        {"content": [{"type": "text", "text": '{"repos":[]}'}]}
    ) == {"repos": []}


def test_snapshot_detects_changed_bytes_and_empty_directories(tmp_path: Path) -> None:
    target = tmp_path / "managed"
    assert LIVE.path_snapshot(target) is None
    target.mkdir()
    (target / "file").write_text("before", encoding="utf-8")
    before = LIVE.path_snapshot(target)
    (target / "file").write_text("after!", encoding="utf-8")
    assert LIVE.path_snapshot(target) != before
    (target / "file").write_text("before", encoding="utf-8")
    assert LIVE.path_snapshot(target) == before
    (target / "empty").mkdir()
    assert LIVE.path_snapshot(target) != before


@pytest.mark.parametrize(
    ("client", "comment_only"),
    [*( (client, False) for client in ClientId), (ClientId.CODEX, True)],
)
def test_lost_unrelated_setting_fails_before_network_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: ClientId, comment_only: bool,
) -> None:
    manifests = load_manifests()
    context = PathContext(PlatformKind.LINUX, tmp_path / "home", {})
    project = tmp_path / "project"
    for item in ClientId:
        adapter = adapter_for(item, manifests, context, project=project)
        initial = (
            "# preserved fixture\nfixturePreserved = true\n"
            if adapter.mcp_target.suffix == ".toml"
            else '{"fixturePreserved": true}\n'
        )
        adapter.mcp_target.parent.mkdir(parents=True, exist_ok=True)
        adapter.mcp_target.write_text(adapter.render_mcp(initial), encoding="utf-8")
        if item is ClientId.CODEX:
            for entry in adapter.jmunch_entries().values():
                executable = Path(str(entry["command"]))
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.write_bytes(b"not executed in this offline config test")
    target = adapter_for(client, manifests, context, project=project).mcp_target
    original = target.read_text(encoding="utf-8")
    changed = (
        original.replace("# preserved fixture", "# lost comment")
        if comment_only else original.replace("true", "false", 1)
    )
    target.write_text(changed, encoding="utf-8")

    # Only the external server boundary is replaced; parsing and entry validation stay real.
    def no_network(*args: object, **kwargs: object) -> None:
        pass

    monkeypatch.setattr(LIVE, "verify_entry", no_network)
    with pytest.raises(AssertionError, match="unrelated fixture"):
        LIVE.verify_saved_entries(
            manifests, context, project, tmp_path, fresh=True, evidence={},
        )
