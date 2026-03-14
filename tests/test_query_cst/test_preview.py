"""
Tests for query_cst command - Preview.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_success_result, write_py_file


class TestQueryCSTCommandPreview:
    """preview=true / dry_run: return diff and modified_source, do not write."""

    @pytest.mark.asyncio
    async def test_preview_returns_diff_and_modified_source(
        self, project_root, mock_db
    ):
        py_file = project_root / "m.py"
        original = "x = 1\ny = 2\n"
        write_py_file(py_file, original)
        with patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ), patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector='smallstmt[type="Assign"]:first',
                replace_with="x = 10",
                preview=True,
            )
        assert_success_result(result)
        assert result.data.get("preview") is True
        assert "diff" in result.data
        assert "modified_source" in result.data
        assert result.data["modified_source"] != original
        assert "x = 10" in result.data["modified_source"]
        assert py_file.read_text(encoding="utf-8") == original

    @pytest.mark.asyncio
    async def test_dry_run_same_as_preview(self, project_root, mock_db):
        py_file = project_root / "m.py"
        original = "a = 1\n"
        write_py_file(py_file, original)
        with patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ), patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                start_line=1,
                end_line=1,
                replace_with="a = 2",
                dry_run=True,
            )
        assert_success_result(result)
        assert result.data.get("preview") is True
        assert "modified_source" in result.data
        assert py_file.read_text(encoding="utf-8") == original
