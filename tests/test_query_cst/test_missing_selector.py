"""
Tests for query_cst command - MissingSelectorOrRange.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_error_result, write_py_file


class TestQueryCSTCommandMissingSelectorOrRange:
    """Query without selector or replace without selector/range."""

    @pytest.mark.asyncio
    async def test_query_without_selector_returns_error(self, project_root, mock_db):
        """Verify test query without selector returns error."""
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
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_MISSING_SELECTOR"

    @pytest.mark.asyncio
    async def test_replace_without_selector_or_range_returns_error(
        self, project_root, mock_db
    ):
        """Verify test replace without selector or range returns error."""
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
                replace_with="y = 1",
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_MISSING_SELECTOR_OR_RANGE"

    @pytest.mark.asyncio
    async def test_range_only_with_replacements_list_returns_error(
        self, project_root, mock_db
    ):
        """Verify test range only with replacements list returns error."""
        py_file = project_root / "m.py"
        write_py_file(py_file, "a = 1\nb = 2\n")
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
                start_line=1,
                end_line=1,
                replacements=[{"match_index": 0, "replace_with": "a = 0"}],
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_RANGE_REPLACEMENTS_NOT_SUPPORTED"
