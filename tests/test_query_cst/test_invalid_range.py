"""
Tests for query_cst command - InvalidRange.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_error_result, write_py_file


class TestQueryCSTCommandInvalidRange:
    """Invalid range: start_line > end_line, out-of-file."""

    @pytest.mark.asyncio
    async def test_start_line_gt_end_line_returns_error(self, project_root, mock_db):
        py_file = project_root / "m.py"
        write_py_file(py_file, "x = 1\n")
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
                start_line=3,
                end_line=1,
                replace_with="pass",
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_INVALID_RANGE"

    @pytest.mark.asyncio
    async def test_range_out_of_file_returns_error(self, project_root, mock_db):
        py_file = project_root / "m.py"
        write_py_file(py_file, "a = 1\nb = 2\n")
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
                end_line=10,
                replace_with="pass",
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_INVALID_RANGE"
