"""
Tests for preview addressing mode (identifier vs invalid-source pagination).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_preview import UniversalFilePreviewCommand
from code_analysis.core.exceptions import ValidationError
from code_analysis.commands.universal_file_preview.errors import (
    INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING,
    INPUT_ERROR_REQUIRES_LINE_ADDRESSING,
)
from code_analysis.commands.universal_file_preview.preview_addressing import (
    check_preview_addressing,
    preview_source_is_parseable,
    uses_identifier_addressing,
    uses_line_fallback_addressing,
)

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


def _db_for(tmp: Path, project_id: str = _PROJECT_UUID) -> MagicMock:
    m = MagicMock()
    row = {
        "id": project_id,
        "root_path": str(tmp.resolve()),
        "watch_dir_id": None,
        "name": "test-project",
    }
    m.select.return_value = [row]
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


def _ensure_project_root(tmp: Path, project_id: str = _PROJECT_UUID) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(json.dumps({"id": project_id}) + "\n", encoding="utf-8")


class TestPreviewAddressingHelpers:
    def test_identifier_addressing_node_ref(self) -> None:
        assert uses_identifier_addressing({"node_ref": "abc"}) is True

    def test_identifier_addressing_selector_slice(self) -> None:
        assert uses_identifier_addressing({"selector": "0:3"}) is True

    def test_line_fallback_only_offset(self) -> None:
        assert uses_line_fallback_addressing({"preview_offset": 100}) is True
        assert uses_line_fallback_addressing({"preview_offset": 0}) is False

    def test_check_invalid_json_with_node_ref(self) -> None:
        err = check_preview_addressing(
            parseable=False,
            params={"node_ref": "/a", "file_path": "x.json"},
            file_path="x.json",
        )
        assert err is not None
        assert err.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING

    def test_check_valid_with_preview_offset(self) -> None:
        err = check_preview_addressing(
            parseable=True,
            params={"preview_offset": 500, "file_path": "x.json"},
            file_path="x.json",
        )
        assert err is not None
        assert err.code == INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING


@pytest.mark.parametrize(
    ("rel", "content"),
    [
        ("broken.json", '{"a": '),
        ("broken.yaml", "key: [unclosed"),
        ("broken.py", "def f(\n"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_structured_file_rejects_identifier_addressing(
    tmp_path: Path, rel: str, content: str
) -> None:
    _ensure_project_root(tmp_path)
    (tmp_path / rel).write_text(content, encoding="utf-8")
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params(
        {
            "project_id": _PROJECT_UUID,
            "file_path": rel,
            "node_ref": "1",
        }
    )
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        result = await cmd.execute(**params)
    assert isinstance(result, ErrorResult)
    assert result.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING


@pytest.mark.parametrize(
    ("rel", "content"),
    [
        ("ok.json", '{"a": 1}\n'),
        ("ok.yaml", "key: value\n"),
        ("ok.py", "def f():\n    return 1\n"),
        ("ok.md", "# Title\n\nbody\n"),
        ("ok.txt", "line one\nline two\n"),
    ],
)
@pytest.mark.asyncio
async def test_parseable_file_rejects_line_pagination(
    tmp_path: Path, rel: str, content: str
) -> None:
    _ensure_project_root(tmp_path)
    (tmp_path / rel).write_text(content, encoding="utf-8")
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params(
        {
            "project_id": _PROJECT_UUID,
            "file_path": rel,
            "preview_offset": 100,
            "max_chars": 500,
        }
    )
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        result = await cmd.execute(**params)
    assert isinstance(result, ErrorResult)
    assert result.code == INPUT_ERROR_REQUIRES_IDENTIFIER_ADDRESSING


@pytest.mark.asyncio
async def test_invalid_json_allows_root_line_pagination(tmp_path: Path) -> None:
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    (tmp_path / rel).write_text('{"x": ' + ("y" * 500), encoding="utf-8")
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params(
        {
            "project_id": _PROJECT_UUID,
            "file_path": rel,
            "max_chars": 200,
            "preview_offset": 0,
        }
    )
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        result = await cmd.execute(**params)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert data.get("focus", {}).get("is_invalid") is True
    assert data.get("mode_notice")
    assert "line-based" in str(data.get("mode_notice")).lower()
    assert isinstance(data.get("preview_chunk"), str)
    assert data.get("preview_has_more") is True


@pytest.mark.asyncio
async def test_valid_json_root_has_no_preview_chunk(tmp_path: Path) -> None:
    _ensure_project_root(tmp_path)
    rel = "ok.json"
    (tmp_path / rel).write_text('{"items": [1, 2, 3]}\n', encoding="utf-8")
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params(
        {
            "project_id": _PROJECT_UUID,
            "file_path": rel,
            "preview_lines": 5,
        }
    )
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        result = await cmd.execute(**params)
    assert isinstance(result, SuccessResult)
    data = result.data
    assert "preview_chunk" not in data
    assert "blocks" in data
    assert "identifier" in str(data.get("mode_notice")).lower()


def test_preview_source_is_parseable_all_formats(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text('{"ok": true}', encoding="utf-8")
    (tmp_path / "b.json").write_text("{bad", encoding="utf-8")
    (tmp_path / "c.txt").write_text("any text", encoding="utf-8")
    assert preview_source_is_parseable(tmp_path / "a.json") is True
    assert preview_source_is_parseable(tmp_path / "b.json") is False
    assert preview_source_is_parseable(tmp_path / "c.txt") is True


def test_schema_node_ref_accepts_integer_short_id() -> None:
    schema = UniversalFilePreviewCommand.get_schema()
    node_ref = schema["properties"]["node_ref"]
    assert "oneOf" in node_ref
    types = {branch.get("type") for branch in node_ref["oneOf"]}
    assert types == {"integer", "string"}


def test_validate_params_accepts_integer_node_ref() -> None:
    cmd = UniversalFilePreviewCommand()
    params = cmd.validate_params(
        {
            "project_id": _PROJECT_UUID,
            "file_path": "src/mod.py",
            "node_ref": 3,
        }
    )
    assert params["node_ref"] == "3"


def test_validate_params_rejects_non_positive_integer_node_ref() -> None:
    cmd = UniversalFilePreviewCommand()
    with pytest.raises(ValidationError):
        cmd.validate_params(
            {
                "project_id": _PROJECT_UUID,
                "file_path": "src/mod.py",
                "node_ref": 0,
            }
        )
