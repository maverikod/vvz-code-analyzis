"""
Tests for query_cst command - Replacements.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from tests.test_query_cst.helpers import (
    assert_error_result,
    assert_success_result,
    write_py_file,
)


class TestQueryCSTCommandReplacements:
    """Test query_cst replace mode with replacements list (different code per match)."""

    @pytest.mark.asyncio
    async def test_replacements_applies_different_code_per_match(
        self, project_root, mock_db
    ):
        """Verify test replacements applies different code per match."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "from a import x\nfrom b import y\nfrom c import z\n",
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
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x, x2"},
                    {"match_index": 1, "code_lines": ["from b import y, y2"]},
                    {"match_index": 2, "replace_with": "from c import z, z2"},
                ],
            )
        assert_success_result(result)
        assert result.data["success"] is True
        assert result.data.get("replaced") == 3
        content = py_file.read_text(encoding="utf-8")
        assert "from a import x, x2" in content
        assert "from b import y, y2" in content
        assert "from c import z, z2" in content

    @pytest.mark.asyncio
    async def test_replacements_legacy_path_unchanged(self, project_root, mock_db):
        """replace_with + replace_all=true still works (no replacements list)."""
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

    @pytest.mark.asyncio
    async def test_replacements_non_sorted_indices(self, project_root, mock_db):
        """Replacements with match_index 2, 0, 1 still apply correctly."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "x = 1\ny = 2\nz = 3\n",
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
                selector='smallstmt[type="Assign"]',
                replacements=[
                    {"match_index": 2, "replace_with": "z = 30"},
                    {"match_index": 0, "replace_with": "x = 10"},
                    {"match_index": 1, "replace_with": "y = 20"},
                ],
            )
        assert_success_result(result)
        assert result.data.get("replaced") == 3
        content = py_file.read_text(encoding="utf-8")
        assert "x = 10" in content
        assert "y = 20" in content
        assert "z = 30" in content

    @pytest.mark.asyncio
    async def test_replacements_no_match_returns_error(self, project_root, mock_db):
        """Verify test replacements no match returns error."""
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
                selector="ImportFrom",
                replacements=[{"match_index": 0, "replace_with": "from a import b"}],
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_NO_MATCH"

    @pytest.mark.asyncio
    async def test_replacements_match_index_out_of_range(self, project_root, mock_db):
        """Verify test replacements match index out of range."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "from a import x\nfrom b import y\n",
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
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x"},
                    {"match_index": 5, "replace_with": "from x import y"},
                ],
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_MATCH_INDEX"

    @pytest.mark.asyncio
    async def test_replacements_duplicate_match_index_returns_error(
        self, project_root, mock_db
    ):
        """Verify test replacements duplicate match index returns error."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "from a import x\nfrom b import y\n",
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
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x"},
                    {"match_index": 0, "replace_with": "from a import x2"},
                ],
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX"

    @pytest.mark.asyncio
    async def test_replacements_missing_code_returns_error(self, project_root, mock_db):
        """Verify test replacements missing code returns error."""
        py_file = project_root / "m.py"
        write_py_file(py_file, "from a import x\n")
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
                selector="ImportFrom",
                replacements=[{"match_index": 0}],
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_REPLACEMENTS_MISSING_CODE"

    @pytest.mark.asyncio
    async def test_replacements_both_code_returns_error(self, project_root, mock_db):
        """Verify test replacements both code returns error."""
        py_file = project_root / "m.py"
        write_py_file(py_file, "from a import x\n")
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
                selector="ImportFrom",
                replacements=[
                    {
                        "match_index": 0,
                        "replace_with": "from a import x",
                        "code_lines": ["from a import x"],
                    },
                ],
            )
        assert_error_result(result)
        assert result.code == "CST_QUERY_REPLACEMENTS_BOTH_CODE"

    @pytest.mark.asyncio
    async def test_replacements_single_backup_and_index_update(
        self, project_root, mock_db
    ):
        """One backup and one index_file call per query_cst replace."""
        py_file = project_root / "m.py"
        write_py_file(
            py_file,
            "from a import x\nfrom b import y\n",
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
            patch(
                "code_analysis.commands.query_cst_handler.BackupManager",
            ) as mock_bm_class,
        ):
            mock_bm = MagicMock()
            mock_bm.create_backup.return_value = "backup-uuid-1"
            mock_bm_class.return_value = mock_bm
            cmd = QueryCSTCommand()
            result = await cmd.execute(
                project_id="test-proj",
                file_path="m.py",
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x2"},
                    {"match_index": 1, "replace_with": "from b import y2"},
                ],
            )
        assert_success_result(result)
        assert mock_bm.create_backup.call_count == 1
        assert mock_db.index_file.call_count == 1
