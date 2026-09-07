"""Guard the live evidence checker against false passes; no network calls."""

import importlib.util
import json
from pathlib import Path

import pytest

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
