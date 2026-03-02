"""
Tests for query_cst MCP command (query and find+replace).

Verifies query-only mode and replace mode (replace_with, code_lines,
match_index, replace_all). Uses tmp_path and mocked database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.query_cst_command import QueryCSTCommand
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


@pytest.fixture
def project_root(tmp_path):
    """Project root as tmp_path."""
    return tmp_path


@pytest.fixture
def mock_db(project_root):
    """Mock database for query_cst (resolve project, index_file after replace)."""
    db = MagicMock()
    db.get_project.return_value = {
        "id": "test-proj",
        "root_path": str(project_root),
    }
    db.index_file.return_value = {"success": True}
    db.disconnect.return_value = None
    return db


def _write_py_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestQueryCSTCommandQueryOnly:
    """Test query_cst without replace (query-only mode)."""

    @pytest.mark.asyncio
    async def test_query_returns_matches_structure(self, project_root, mock_db):
        py_file = project_root / "src" / "main.py"
        _write_py_file(
            py_file,
            "def foo():\n    return 1\n\ndef bar():\n    return 2\n",
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
                file_path="src/main.py",
                selector="function",
            )
        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
        assert "matches" in result.data
        assert result.data["selector"] == "function"
        assert len(result.data["matches"]) == 2

    @pytest.mark.asyncio
    async def test_query_with_selector_returns_matching_nodes(
        self, project_root, mock_db
    ):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "def first():\n    return 1\n\ndef second():\n    return 2\n",
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
                selector='function[name="first"]',
            )
        assert isinstance(result, SuccessResult)
        assert len(result.data["matches"]) == 1
        assert result.data["matches"][0]["name"] == "first"


class TestQueryCSTCommandReplace:
    """Test query_cst replace mode (replace_with / code_lines)."""

    @pytest.mark.asyncio
    async def test_replace_first_return_with_replace_with(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "def foo():\n    return 1\n",
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
                selector='function[name="foo"] smallstmt[type="Return"]:first',
                replace_with="return 42",
            )
        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
        assert result.data.get("replaced") == 1
        assert "backup_uuid" in result.data
        content = py_file.read_text(encoding="utf-8")
        assert "return 42" in content
        assert "return 1" not in content

    @pytest.mark.asyncio
    async def test_replace_with_code_lines(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "def bar():\n    pass\n",
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
                selector='function[name="bar"] smallstmt[type="Pass"]:first',
                code_lines=["raise NotImplementedError()"],
            )
        assert isinstance(result, SuccessResult)
        assert result.data.get("replaced") == 1
        content = py_file.read_text(encoding="utf-8")
        assert "raise NotImplementedError()" in content
        assert "pass" not in content or "NotImplementedError" in content

    @pytest.mark.asyncio
    async def test_replace_all_matches(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "def a():\n    pass\ndef b():\n    pass\n",
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
                selector='smallstmt[type="Pass"]',
                replace_with="return None",
                replace_all=True,
            )
        assert isinstance(result, SuccessResult)
        assert result.data.get("replaced") == 2
        content = py_file.read_text(encoding="utf-8")
        assert content.count("return None") == 2
        assert "pass" not in content

    @pytest.mark.asyncio
    async def test_replace_no_match_returns_error(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(py_file, "x = 1\n")
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
                selector='function[name="nonexistent"]',
                replace_with="pass",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_NO_MATCH"

    @pytest.mark.asyncio
    async def test_replace_match_index_out_of_range_returns_error(
        self, project_root, mock_db
    ):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "def f():\n    return 1\n",
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
                selector="function",
                replace_with="def f(): pass",
                match_index=5,
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_MATCH_INDEX"


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
        assert isinstance(result, ErrorResult)
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
        assert isinstance(result, ErrorResult)
        assert result.code == "FILE_NOT_FOUND"


class TestQueryCSTCommandReplacements:
    """Test query_cst replace mode with replacements list (different code per match)."""

    @pytest.mark.asyncio
    async def test_replacements_applies_different_code_per_match(
        self, project_root, mock_db
    ):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "from a import x\nfrom b import y\nfrom c import z\n",
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
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x, x2"},
                    {"match_index": 1, "code_lines": ["from b import y, y2"]},
                    {"match_index": 2, "replace_with": "from c import z, z2"},
                ],
            )
        assert isinstance(result, SuccessResult)
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
        _write_py_file(
            py_file,
            "def a():\n    pass\ndef b():\n    pass\n",
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
                selector='smallstmt[type="Pass"]',
                replace_with="return None",
                replace_all=True,
            )
        assert isinstance(result, SuccessResult)
        assert result.data.get("replaced") == 2
        content = py_file.read_text(encoding="utf-8")
        assert content.count("return None") == 2

    @pytest.mark.asyncio
    async def test_replacements_non_sorted_indices(self, project_root, mock_db):
        """Replacements with match_index 2, 0, 1 still apply correctly."""
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "x = 1\ny = 2\nz = 3\n",
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
                selector='smallstmt[type="Assign"]',
                replacements=[
                    {"match_index": 2, "replace_with": "z = 30"},
                    {"match_index": 0, "replace_with": "x = 10"},
                    {"match_index": 1, "replace_with": "y = 20"},
                ],
            )
        assert isinstance(result, SuccessResult)
        assert result.data.get("replaced") == 3
        content = py_file.read_text(encoding="utf-8")
        assert "x = 10" in content
        assert "y = 20" in content
        assert "z = 30" in content

    @pytest.mark.asyncio
    async def test_replacements_no_match_returns_error(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(py_file, "x = 1\n")
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
                selector="ImportFrom",
                replacements=[{"match_index": 0, "replace_with": "from a import b"}],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_NO_MATCH"

    @pytest.mark.asyncio
    async def test_replacements_match_index_out_of_range(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "from a import x\nfrom b import y\n",
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
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x"},
                    {"match_index": 5, "replace_with": "from x import y"},
                ],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_MATCH_INDEX"

    @pytest.mark.asyncio
    async def test_replacements_duplicate_match_index_returns_error(
        self, project_root, mock_db
    ):
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "from a import x\nfrom b import y\n",
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
                selector="ImportFrom",
                replacements=[
                    {"match_index": 0, "replace_with": "from a import x"},
                    {"match_index": 0, "replace_with": "from a import x2"},
                ],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX"

    @pytest.mark.asyncio
    async def test_replacements_missing_code_returns_error(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(py_file, "from a import x\n")
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
                selector="ImportFrom",
                replacements=[{"match_index": 0}],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_REPLACEMENTS_MISSING_CODE"

    @pytest.mark.asyncio
    async def test_replacements_both_code_returns_error(self, project_root, mock_db):
        py_file = project_root / "m.py"
        _write_py_file(py_file, "from a import x\n")
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
                selector="ImportFrom",
                replacements=[
                    {
                        "match_index": 0,
                        "replace_with": "from a import x",
                        "code_lines": ["from a import x"],
                    },
                ],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_QUERY_REPLACEMENTS_BOTH_CODE"

    @pytest.mark.asyncio
    async def test_replacements_single_backup_and_index_update(
        self, project_root, mock_db
    ):
        """One backup and one index_file call per query_cst replace."""
        py_file = project_root / "m.py"
        _write_py_file(
            py_file,
            "from a import x\nfrom b import y\n",
        )
        with patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ), patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch(
            "code_analysis.commands.query_cst_command.BackupManager",
        ) as mock_bm_class:
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
        assert isinstance(result, SuccessResult)
        assert mock_bm.create_backup.call_count == 1
        assert mock_db.index_file.call_count == 1
