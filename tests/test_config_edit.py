import json

import pytest
import tomlkit

from three_layer_installer.config_edit import (
    ConfigError,
    set_jsonc_path,
    set_owned_block,
    set_toml_path,
)


def test_json_path_is_created_from_empty_object() -> None:
    updated = set_jsonc_path("{}\n", ("mcpServers", "jcodemunch"), {"command": "uvx"})

    assert json.loads(updated)["mcpServers"]["jcodemunch"] == {"command": "uvx"}
    assert updated.endswith("\n")


def test_jsonc_merge_preserves_comments_trailing_commas_and_unrelated_secret() -> None:
    original = """{
  // keep this comment
  "apiToken": "fixture-secret-value",
  "mcp": {
    "existing": {"enabled": true},
  },
}
"""

    updated = set_jsonc_path(
        original,
        ("mcp", "jcodemunch"),
        {"type": "local", "command": ["uvx", "jcodemunch-mcp"]},
    )

    assert "// keep this comment" in updated
    assert '"apiToken": "fixture-secret-value"' in updated
    assert '"existing": {"enabled": true},' in updated
    assert '"jcodemunch"' in updated


def test_jsonc_existing_value_is_replaced_without_reformatting_other_keys() -> None:
    original = '{\n  "mcpServers": {"jdocmunch": {"command": "old"}},\n  "theme": "dark"\n}\n'

    updated = set_jsonc_path(
        original,
        ("mcpServers", "jdocmunch"),
        {"command": "uvx", "args": ["new"]},
    )

    assert '"theme": "dark"' in updated
    assert '"command": "old"' not in updated
    assert json.loads(updated)["mcpServers"]["jdocmunch"]["args"] == ["new"]


def test_invalid_jsonc_fails_closed() -> None:
    with pytest.raises(ConfigError, match="invalid JSONC"):
        set_jsonc_path('{"broken": ', ("mcpServers",), {})


def test_toml_merge_preserves_comments_and_unrelated_values() -> None:
    original = '# keep this comment\nmodel = "example"\napi_key = "fixture-secret-value"\n'

    updated = set_toml_path(
        original,
        ("mcp_servers", "jdatamunch"),
        {"command": "uvx", "args": ["jdatamunch-mcp"]},
    )
    parsed = tomlkit.parse(updated)

    assert "# keep this comment" in updated
    assert parsed["api_key"] == "fixture-secret-value"
    assert parsed["mcp_servers"]["jdatamunch"]["command"] == "uvx"


def test_owned_instruction_block_is_idempotently_replaced() -> None:
    original = "# User instructions\n\nKeep this paragraph.\n"
    first = set_owned_block(original, "rtk-routing", "Use `rtk` for supported commands.")
    second = set_owned_block(first, "rtk-routing", "Use `rtk` whenever it is available.")

    assert "Keep this paragraph." in second
    assert second.count("three-layer:rtk-routing:start") == 1
    assert "Use `rtk` for supported commands." not in second
    assert "Use `rtk` whenever it is available." in second
