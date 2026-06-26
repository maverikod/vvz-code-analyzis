"""
Tests for query_cst command - QueryOnly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import assert_success_result, write_py_file


class TestQueryCSTCommandQueryOnly:
    """Test query_cst without replace (query-only mode)."""

    @pytest.mark.asyncio
    async def test_query_returns_matches_structure(self, project_root, mock_db):
        """Verify test query returns matches structure."""
        py_file = project_root / "src" / "main.py"
        write_py_file(
            py_file,
            "def foo():\n    return 1\n\ndef bar():\n    return 2\n",
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
                file_path="src/main.py",
                selector="function",
            )
        assert_success_result(result)
        assert result.data["success"] is True
        assert "matches" in result.data
        assert result.data["selector"] == "function"
        assert len(result.data["matches"]) == 2

    @pytest.mark.asyncio
    async def test_query_with_selector_returns_matching_nodes(
        self, project_root, mock_db
    ):
        """Verify test query with selector returns matching nodes."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "def first():\n    return 1\n\ndef second():\n    return 2\n",
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
                selector='function[name="first"]',
            )
        assert_success_result(result)
        assert len(result.data["matches"]) == 1
        assert result.data["matches"][0]["name"] == "first"
