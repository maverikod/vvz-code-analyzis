"""Tests for comment-aware config.json loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.config_json import (
    ConfigJSONDecodeError,
    load_config_json,
    load_config_json_text,
)


def test_load_config_json_text_plain_json() -> None:
    """Verify test load config json text plain json."""
    data = load_config_json_text('{"server": {"port": 15000}}')
    assert data["server"]["port"] == 15000


def test_load_config_json_text_with_hash_comments() -> None:
    """Verify test load config json text with hash comments."""
    text = """
# deployment config
{
  "code_analysis": {
    "database": {
      "driver": {
        "config": {"port": 5433}
      }
    }
  }
}
"""
    data = load_config_json_text(text)
    assert data["code_analysis"]["database"]["driver"]["config"]["port"] == 5433


def test_load_config_json_text_rejects_non_object_root() -> None:
    """Verify test load config json text rejects non object root."""
    with pytest.raises(ConfigJSONDecodeError, match="JSON object"):
        load_config_json_text("[1, 2]")


def test_load_config_json_from_file(tmp_path: Path) -> None:
    """Verify test load config json from file."""
    path = tmp_path / "config.json"
    path.write_text(
        '# comment\n{"server": {"host": "127.0.0.1"}}\n',
        encoding="utf-8",
    )
    data = load_config_json(path)
    assert data["server"]["host"] == "127.0.0.1"
