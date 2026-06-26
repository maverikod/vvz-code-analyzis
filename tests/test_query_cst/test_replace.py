"""
Tests for query_cst command - Replace.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import (
    assert_error_result,
    assert_success_result,
    write_py_file,
)


class TestQueryCSTCommandReplace:
    """Test query_cst replace mode (replace_with / code_lines)."""

    @pytest.mark.asyncio
    async def test_replace_first_return_with_replace_with(self, project_root, mock_db):
        """Verify test replace first return with replace with."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "def foo():\n    return 1\n",
        )
        with (
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=project_root,
            ),
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector='function[name="foo"] smallstmt[type="Return"]:first',
                replace_with="return 42",
            )
        assert_success_result(result)
        assert result.data["success"] is True
        assert result.data.get("replaced") == 1
        assert "backup_uuid" in result.data
        content = py_file.read_text(encoding="utf-8")
        assert "return 42" in content
        assert "return 1" not in content

    @pytest.mark.asyncio
    async def test_replace_with_code_lines(self, project_root, mock_db):
        """Verify test replace with code lines."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "def bar():\n    pass\n",
        )
        with (
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=project_root,
            ),
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector='function[name="bar"] smallstmt[type="Pass"]:first',
                code_lines=["raise NotImplementedError()"],
            )
        assert_success_result(result)
        assert result.data.get("replaced") == 1
        content = py_file.read_text(encoding="utf-8")
        assert "raise NotImplementedError()" in content
        assert "pass" not in content or "NotImplementedError" in content

    @pytest.mark.asyncio
    async def test_replace_all_matches(self, project_root, mock_db):
        """Verify test replace all matches."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "def a():\n    pass\ndef b():\n    pass\n",
        )
        with (
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=project_root,
            ),
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector='smallstmt[type="Pass"]',
                replace_with="return None",
                replace_all=True,
            )
        assert_success_result(result)
        assert result.data.get("replaced") == 2
        content = py_file.read_text(encoding="utf-8")
        assert content.count("return None") == 2
        assert "pass" not in content

    @pytest.mark.asyncio
    async def test_replace_no_match_returns_error(self, project_root, mock_db):
        """Verify test replace no match returns error."""
        py_file = project_root / "m.py"
        write_py_file(py_file, "x = 1\n")
        with (
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=project_root,
            ),
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector='function[name="nonexistent"]',
                replace_with="pass",
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_NO_MATCH"

    @pytest.mark.asyncio
    async def test_replace_match_index_out_of_range_returns_error(
        self, project_root, mock_db
    ):
        """Verify test replace match index out of range returns error."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "def f():\n    return 1\n",
        )
        with (
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=project_root,
            ),
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
        ):
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector="function",
                replace_with="def f(): pass",
                match_index=5,
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_MATCH_INDEX"
