"""
Smoke tests for universal_file_preview (no MCP; unit-level).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_analysis.commands.read_only_batch_whitelist import READ_ONLY_BATCH_WHITELIST
from code_analysis.commands.universal_file_preview import UniversalFilePreviewCommand
from code_analysis.commands.universal_file_preview.dispatcher import HandlerDispatcher
from code_analysis.commands.universal_file_preview.errors import (
    INPUT_ERROR_CONFLICTING_PARAMETERS,
    INPUT_ERROR_UNKNOWN_EXTENSION,
    PreviewError,
)
from code_analysis.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.jsonl_handler import (
    JsonLinesFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.python_handler import (
    PythonFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.text_handler import (
    TextFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.yaml_handler import (
    YamlFileHandler,
)
from code_analysis.commands.universal_file_preview.models import NodeKind
from code_analysis.commands.universal_file_preview.session import resolve_session


def test_command_name_and_schema_structure() -> None:
    """Command name and shallow schema layout for MCP integration."""
    assert UniversalFilePreviewCommand.name == "universal_file_preview"
    schema = UniversalFilePreviewCommand.get_schema()
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    props = schema.get("properties")
    assert isinstance(props, dict)
    assert "project_id" in props
    assert "file_path" in props


def test_handler_dispatcher_known_and_unknown_extensions() -> None:
    """Dispatch maps extensions to handlers; unknown extension is PreviewError."""
    d = HandlerDispatcher()
    py_h = d.dispatch("a.py")
    assert isinstance(py_h, PythonFileHandler)
    md_h = d.dispatch("notes.md")
    assert isinstance(md_h, TextFileHandler)
    json_h = d.dispatch("cfg.json")
    assert isinstance(json_h, JsonFileHandler)
    yaml_h = d.dispatch("cfg.yaml")
    assert isinstance(yaml_h, YamlFileHandler)
    jsonl_h = d.dispatch("data.jsonl")
    assert isinstance(jsonl_h, JsonLinesFileHandler)

    bad = d.dispatch("x.xml")
    assert isinstance(bad, PreviewError)
    assert bad.code == INPUT_ERROR_UNKNOWN_EXTENSION


def test_resolve_session_unknown_tree_id_returns_preview_error() -> None:
    """Unknown caller tree_id surfaces as input PreviewError (registry miss)."""
    handler = MagicMock()
    bogus = "00000000-0000-4000-8000-000000000099"
    out = resolve_session(handler, {"tree_id": bogus})
    assert isinstance(out, PreviewError)
    assert out.code == INPUT_ERROR_CONFLICTING_PARAMETERS


def test_python_handler_open_root_valid_syntax(tmp_path) -> None:
    path = tmp_path / "t.py"
    path.write_text("x = 1\n", encoding="utf-8")
    result = PythonFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.TREE_NODE


def test_text_handler_open_root_lines_kind(tmp_path) -> None:
    path = tmp_path / "t.md"
    path.write_text("single line\n", encoding="utf-8")
    result = TextFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.LINES


def test_json_handler_open_root_mapping_kind(tmp_path) -> None:
    path = tmp_path / "t.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    result = JsonFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.MAPPING


def test_yaml_handler_open_root_mapping_kind(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "t.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    result = YamlFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.MAPPING


def test_jsonl_handler_open_root_lines_kind(tmp_path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"x":1}\n', encoding="utf-8")
    result = JsonLinesFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.LINES


def test_universal_file_preview_whitelisted_for_read_only_batch() -> None:
    """Read-only batch allows universal_file_preview."""
    assert "universal_file_preview" in READ_ONLY_BATCH_WHITELIST
