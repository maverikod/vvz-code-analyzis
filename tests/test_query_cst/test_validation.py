"""
Tests for query_cst command - Validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_error_result, write_py_file


class TestQueryCSTCommandValidation:
    """Test query_cst validation and error codes."""

    @pytest.mark.asyncio
    async def test_invalid_file_extension(self, project_root, mock_db):
        txt_file = project_root / "readme.txt"
        txt_file.write_text("hello", encoding="utf-8")
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
                file_path="readme.txt",
                selector="function",
            )
        assert_error_result(result)
        assert result.code == "INVALID_FILE"

    @pytest.mark.asyncio
    async def test_file_not_found(self, project_root, mock_db):
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
                file_path="nonexistent.py",
                selector="function",
            )
        assert_error_result(result)
        assert result.code == "FILE_NOT_FOUND"
