"""
Tests for query_cst command - SelectorRangeInteraction.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_success_result, write_py_file


class TestQueryCSTCommandSelectorRangeInteraction:
    """Selector-only, range-only, both (range takes precedence)."""

    @pytest.mark.asyncio
    async def test_selector_only_replace_unchanged(self, project_root, mock_db):
        """Verify test selector only replace unchanged."""
        py_file = project_root / "m.py"
        write_py_file(py_file, "def f():\n    return 1\n")
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
                selector='smallstmt[type="Return"]:first',
                replace_with="return 2",
            )
        assert_success_result(result)
        assert "return 2" in py_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_both_selector_and_range_range_used(self, project_root, mock_db):
        """Verify test both selector and range range used."""
        py_file = project_root / "m.py"
        write_py_file(py_file, "a = 1\nb = 2\nc = 3\n")
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
                selector="smallstmt",
                start_line=2,
                end_line=2,
                replace_with="b = 20",
            )
        assert_success_result(result)
        content = py_file.read_text(encoding="utf-8")
        lines = content.strip().splitlines()
        assert lines[1] == "b = 20"
