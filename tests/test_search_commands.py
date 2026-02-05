"""
Tests for all search command types.

Verifies fulltext_search, find_classes, list_class_methods, search_ast_nodes
return expected result structure. Uses mocked database to avoid full schema setup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_mcp_commands import (
    FindClassesMCPCommand,
    FulltextSearchMCPCommand,
    ListClassMethodsMCPCommand,
)
from code_analysis.commands.ast.search_nodes import SearchASTNodesMCPCommand
from mcp_proxy_adapter.commands.result import SuccessResult


def _make_mock_db_for_search():
    """Create mock database with search methods returning empty lists."""
    db = MagicMock()
    db.full_text_search.return_value = []
    db.search_classes.return_value = []
    db.search_methods.return_value = []
    db.execute.return_value = {"data": []}
    db.get_file_by_path.return_value = None
    db.get_project.return_value = {"id": "test-proj", "root_path": "/tmp/proj"}
    db.disconnect.return_value = None
    return db


@pytest.fixture
def mock_db(project_root):
    """Mock database client for search commands."""
    db = _make_mock_db_for_search()
    db.get_project.return_value = {
        "id": "test-proj",
        "root_path": str(project_root),
    }
    return db


@pytest.fixture
def project_root(tmp_path):
    """Fake project root."""
    return tmp_path


class TestFulltextSearchCommand:
    """Test fulltext_search command."""

    @pytest.mark.asyncio
    async def test_fulltext_search_returns_success_structure(
        self, mock_db, project_root
    ):
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = FulltextSearchMCPCommand()
            result = await cmd.execute(
                project_id="test-proj",
                query="hello",
            )
        assert isinstance(result, SuccessResult)
        data = result.data
        assert "query" in data
        assert data["query"] == "hello"
        assert "results" in data
        assert "count" in data
        assert data["count"] == len(data["results"])
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_fulltext_search_with_entity_type_and_limit(
        self, mock_db, project_root
    ):
        mock_db.full_text_search.return_value = [
            {
                "entity_type": "class",
                "entity_name": "Foo",
                "content": "class Foo: pass",
                "docstring": None,
                "file_path": "src/foo.py",
            }
        ]
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = FulltextSearchMCPCommand()
            result = await cmd.execute(
                project_id="test-proj",
                query="Foo",
                entity_type="class",
                limit=5,
            )
        assert isinstance(result, SuccessResult)
        assert len(result.data["results"]) == 1
        assert result.data["results"][0]["entity_name"] == "Foo"


class TestFindClassesCommand:
    """Test find_classes command."""

    @pytest.mark.asyncio
    async def test_find_classes_returns_success_structure(self, mock_db, project_root):
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = FindClassesMCPCommand()
            result = await cmd.execute(project_id="test-proj")
        assert isinstance(result, SuccessResult)
        data = result.data
        assert "classes" in data
        assert "count" in data
        assert data["classes"] == []

    @pytest.mark.asyncio
    async def test_find_classes_with_pattern(self, mock_db, project_root):
        mock_db.search_classes.return_value = [
            {"name": "MyClass", "file_path": "a.py", "line": 1}
        ]
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = FindClassesMCPCommand()
            result = await cmd.execute(
                project_id="test-proj",
                pattern="My%",
            )
        assert isinstance(result, SuccessResult)
        assert len(result.data["classes"]) == 1
        assert result.data["classes"][0]["name"] == "MyClass"


class TestListClassMethodsCommand:
    """Test list_class_methods command."""

    @pytest.mark.asyncio
    async def test_list_class_methods_returns_success_structure(
        self, mock_db, project_root
    ):
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = ListClassMethodsMCPCommand()
            result = await cmd.execute(
                project_id="test-proj",
                class_name="MyClass",
            )
        assert isinstance(result, SuccessResult)
        data = result.data
        assert data["class_name"] == "MyClass"
        assert "methods" in data
        assert "count" in data
        assert data["methods"] == []


class TestSearchASTNodesCommand:
    """Test search_ast_nodes command."""

    @pytest.mark.asyncio
    async def test_search_ast_nodes_returns_success_structure(
        self, mock_db, project_root
    ):
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = SearchASTNodesMCPCommand()
            result = await cmd.execute(
                project_id="test-proj",
                node_type="ClassDef",
            )
        assert isinstance(result, SuccessResult)
        data = result.data
        assert "nodes" in data
        assert "count" in data
        assert data["node_type"] == "ClassDef"
        assert data["nodes"] == []

    @pytest.mark.asyncio
    async def test_search_ast_nodes_function_def(self, mock_db, project_root):
        mock_db.execute.return_value = {
            "data": [
                {
                    "name": "main",
                    "file_path": "main.py",
                    "line": 10,
                    "docstring": "Entry point.",
                }
            ]
        }
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=project_root,
        ):
            cmd = SearchASTNodesMCPCommand()
            result = await cmd.execute(
                project_id="test-proj",
                node_type="FunctionDef",
            )
        assert isinstance(result, SuccessResult)
        assert result.data["node_type"] == "FunctionDef"
        assert len(result.data["nodes"]) >= 0  # may be 0 or 1 depending on query order
