"""
Tests for query_cst command - LineRangeReplace.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_success_result, write_py_file


class TestQueryCSTCommandLineRangeReplace:
    """Replace by start_line/end_line only (no selector)."""

    @pytest.mark.asyncio
    async def test_replace_by_line_range_only(self, project_root, mock_db):
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "a = 1\nb = 2\nc = 3\n",
        )
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
                start_line=2,
                end_line=2,
                replace_with="b = 20",
            )
        assert_success_result(result)
        assert result.data.get("replaced") == 1
        content = py_file.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert lines[1] == "b = 20"
        assert "a = 1" in content
        assert "c = 3" in content

    @pytest.mark.asyncio
    async def test_replace_by_line_range_multiline(self, project_root, mock_db):
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "def foo():\n    return 1\n\nx = 0\n",
        )
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
                end_line=2,
                code_lines=["def foo():", "    return 42"],
            )
        assert_success_result(result)
        assert result.data.get("replaced") == 1
        content = py_file.read_text(encoding="utf-8")
        assert "return 42" in content
        assert "return 1" not in content
