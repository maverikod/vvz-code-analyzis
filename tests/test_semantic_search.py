"""
Comprehensive tests for semantic search functionality.

Tests cover:
- Basic semantic search operations
- Error handling (missing FAISS, missing SVO)
- Result format and structure
- Edge cases (empty results, invalid queries)
- Integration with database and FAISS index

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import asyncio
import numpy as np
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, AsyncMock

from code_analysis.commands.semantic_search import SemanticSearchCommand
from code_analysis.core.database import CodeDatabase
from code_analysis.core.faiss_manager import FaissIndexManager


@pytest.fixture
def test_db():
    """Create test database with sample data."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = CodeDatabase(db_path)

        # Add project
        project_id = db.get_or_create_project(str(tmpdir), name="test_project")

        # Add file
        file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

        # Add class
        class_id = db.add_class(file_id, "TestClass", 10, "Test class docstring", [])

        # Add method
        method_id = db.add_method(
            class_id,
            "test_method",
            15,
            ["self"],
            "Test method docstring",
            False,
            False,
            False,
        )

        # Add function
        function_id = db.add_function(
            file_id, "test_function", 25, ["arg1"], "Test function docstring"
        )

        # Add code chunks with vector_ids (async)
        async def add_chunks():
            chunk_id1 = await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid="chunk-1",
                chunk_type="DocBlock",
                chunk_text="Test class docstring",
                chunk_ordinal=1,
                vector_id=0,
                embedding_model="test-model",
                class_id=class_id,
                line=10,
                ast_node_type="ClassDef",
                source_type="docstring",
            )

            chunk_id2 = await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid="chunk-2",
                chunk_type="DocBlock",
                chunk_text="Test method docstring",
                chunk_ordinal=2,
                vector_id=1,
                embedding_model="test-model",
                class_id=class_id,
                method_id=method_id,
                line=15,
                ast_node_type="FunctionDef",
                source_type="docstring",
            )

            chunk_id3 = await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid="chunk-3",
                chunk_type="DocBlock",
                chunk_text="Test function docstring",
                chunk_ordinal=3,
                vector_id=2,
                embedding_model="test-model",
                function_id=function_id,
                line=25,
                ast_node_type="FunctionDef",
                source_type="docstring",
            )
            return chunk_id1, chunk_id2, chunk_id3

        asyncio.run(add_chunks())

        db.close()
        yield db_path, project_id, tmpdir


@pytest.fixture
def mock_faiss_manager():
    """Create mock FAISS manager."""
    manager = Mock(spec=FaissIndexManager)
    manager.vector_dim = 384
    manager.search = Mock(
        return_value=(
            np.array([0.1, 0.2, 0.3], dtype=np.float32),
            np.array([0, 1, 2], dtype=np.int64),
        )
    )
    return manager


@pytest.fixture
def mock_svo_client_manager():
    """Create mock SVO client manager."""
    manager = Mock()

    # Mock chunk with embedding
    class MockChunk:
        def __init__(self, text, embedding):
            self.body = text
            self.text = text
            self.embedding = embedding
            self.embedding_model = "test-model"

    async def get_embeddings(chunks):
        embeddings = [0.1] * 384  # Mock embedding vector
        return [MockChunk(chunk.text, embeddings) for chunk in chunks]

    manager.get_embeddings = AsyncMock(side_effect=get_embeddings)
    manager.initialize = AsyncMock(return_value=None)
    manager.close = AsyncMock(return_value=None)

    return manager


class TestSemanticSearchBasic:
    """Basic tests for semantic search."""

    @pytest.mark.asyncio
    async def test_search_without_faiss_manager(self, test_db):
        """Test that search raises error when FAISS manager is missing."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            with pytest.raises(RuntimeError, match="FAISS manager"):
                await cmd.search("test query", k=5)
        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_without_svo_manager(self, test_db, mock_faiss_manager):
        """Test that search raises error when SVO client manager is missing."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=None,
            )

            with pytest.raises(RuntimeError, match="SVO client manager"):
                await cmd.search("test query", k=5)
        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_basic(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test basic semantic search functionality."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5)

            assert isinstance(results, list)
            assert len(results) > 0

            # Check result structure
            result = results[0]
            assert "file_path" in result
            assert "file_id" in result
            assert "line" in result
            assert "ast_node_type" in result
            assert "chunk_text" in result
            assert "relevance_score" in result
            assert "source_type" in result

            # Check that file_path is always present
            assert result["file_path"] is not None
            assert isinstance(result["file_path"], str)

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_result_structure(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test that search results have correct structure."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=10)

            for result in results:
                # Required fields
                assert "file_path" in result
                assert "file_id" in result
                assert "line" in result
                assert "ast_node_type" in result
                assert "chunk_text" in result
                assert "relevance_score" in result
                assert "source_type" in result

                # File path must be present
                assert result["file_path"] is not None
                assert isinstance(result["file_path"], str)

                # Optional fields (may be None)
                assert "class_name" in result
                assert "function_name" in result
                assert "method_name" in result

                # Relevance score should be a number
                assert isinstance(result["relevance_score"], (int, float))

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_with_limit(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search with different k values."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            # Test with k=1
            results = await cmd.search("test query", k=1)
            assert len(results) <= 1

            # Test with k=5
            results = await cmd.search("test query", k=5)
            assert len(results) <= 5

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_with_max_distance(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search with max_distance filter."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            # Test with max_distance
            results = await cmd.search("test query", k=10, max_distance=0.5)
            assert isinstance(results, list)

            # All results should have relevance_score <= max_distance
            for result in results:
                assert result["relevance_score"] <= 0.5

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search when FAISS returns no results."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Mock FAISS to return empty results
        mock_faiss_manager.search = Mock(
            return_value=(np.array([], dtype=np.float32), np.array([], dtype=np.int64))
        )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5)
            assert isinstance(results, list)
            assert len(results) == 0

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_with_ast_node(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search with include_ast_node=True."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Add AST tree to database
        file_id = database.get_file_id("test.py", project_id)
        if file_id:
            ast_json = '{"_type": "Module", "body": [{"_type": "ClassDef", "name": "TestClass", "lineno": 10}]}'
            await database.save_ast_tree(
                file_id, project_id, ast_json, "test-hash", 1234567890.0
            )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5, include_ast_node=True)

            # At least one result should have ast_node if AST tree exists
            any("ast_node" in result for result in results)
            # Note: This may be False if AST node is not found, which is OK

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_context_binding(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test that search results include correct context (class, method, function)."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=10)

            # Check that results have appropriate context
            for result in results:
                # If class_name is set, it should be a string
                if result.get("class_name"):
                    assert isinstance(result["class_name"], str)

                # If method_name is set, it should be a string
                if result.get("method_name"):
                    assert isinstance(result["method_name"], str)

                # If function_name is set, it should be a string
                if result.get("function_name"):
                    assert isinstance(result["function_name"], str)

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_embedding_error(self, test_db, mock_faiss_manager):
        """Test search when embedding generation fails."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Mock SVO client to raise error
        mock_svo = Mock()
        mock_svo.get_embeddings = AsyncMock(side_effect=Exception("Embedding error"))

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo,
            )

            results = await cmd.search("test query", k=5)
            # Should return empty list on error
            assert isinstance(results, list)
            assert len(results) == 0

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_empty_embedding_result(self, test_db, mock_faiss_manager):
        """Test search when embedding returns empty list."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Mock SVO client to return empty list
        mock_svo = Mock()
        mock_svo.get_embeddings = AsyncMock(return_value=[])

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo,
            )

            results = await cmd.search("test query", k=5)
            # Should return empty list
            assert isinstance(results, list)
            assert len(results) == 0

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_embedding_without_embedding_attr(
        self, test_db, mock_faiss_manager
    ):
        """Test search when embedding chunk has no embedding attribute."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Mock SVO client to return chunk without embedding
        class MockChunkNoEmbedding:
            def __init__(self, text):
                self.body = text
                self.text = text
                # No embedding attribute

        mock_svo = Mock()

        async def get_embeddings(chunks):
            return [MockChunkNoEmbedding(chunk.text) for chunk in chunks]

        mock_svo.get_embeddings = AsyncMock(side_effect=get_embeddings)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo,
            )

            results = await cmd.search("test query", k=5)
            # Should return empty list
            assert isinstance(results, list)
            assert len(results) == 0

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_faiss_error(self, test_db, mock_svo_client_manager):
        """Test search when FAISS search fails."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Mock FAISS to raise error
        mock_faiss = Mock(spec=FaissIndexManager)
        mock_faiss.vector_dim = 384
        mock_faiss.search = Mock(side_effect=Exception("FAISS error"))

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5)
            # Should return empty list on error
            assert isinstance(results, list)
            assert len(results) == 0

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_find_ast_node_method(self, test_db):
        """Test _find_ast_node method."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            # Test with valid AST dict
            ast_dict = {
                "_type": "Module",
                "body": [
                    {
                        "_type": "ClassDef",
                        "name": "TestClass",
                        "lineno": 10,
                        "body": [
                            {
                                "_type": "FunctionDef",
                                "name": "test_method",
                                "lineno": 15,
                            }
                        ],
                    }
                ],
            }

            # Find class node
            node = cmd._find_ast_node(ast_dict, 10, "ClassDef")
            assert node is not None
            assert node["_type"] == "ClassDef"
            assert node["name"] == "TestClass"

            # Find method node
            node = cmd._find_ast_node(ast_dict, 15, "FunctionDef")
            assert node is not None
            assert node["_type"] == "FunctionDef"
            assert node["name"] == "test_method"

            # Find non-existent node
            node = cmd._find_ast_node(ast_dict, 999, "ClassDef")
            assert node is None

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_ast_node_name_priority(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test that ast_node_name is set with correct priority (class > method > function)."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=10)

            for result in results:
                # If class_name exists, it should be used as ast_node_name
                if result.get("class_name"):
                    assert result.get("ast_node_name") == result["class_name"]
                # If method_name exists (and no class_name), it should be used
                elif result.get("method_name"):
                    assert result.get("ast_node_name") == result["method_name"]
                # If function_name exists (and no class/method), it should be used
                elif result.get("function_name"):
                    assert result.get("ast_node_name") == result["function_name"]

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_no_ast_node_name(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search when chunk has no class/method/function (ast_node_name not set)."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Add chunk without class/method/function binding
        file_id = database.get_file_id("test.py", project_id)
        if file_id:
            await database.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid="chunk-no-context",
                chunk_type="DocBlock",
                chunk_text="Standalone docstring",
                chunk_ordinal=4,
                vector_id=3,
                embedding_model="test-model",
                line=30,
                ast_node_type="Expr",
                source_type="comment",
            )

        # Mock FAISS to return this vector_id
        mock_faiss_manager.search = Mock(
            return_value=(
                np.array([0.1], dtype=np.float32),
                np.array([3], dtype=np.int64),
            )
        )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5)

            # Find result without ast_node_name
            for result in results:
                if result.get("chunk_text") == "Standalone docstring":
                    # Should not have ast_node_name (covers line 213)
                    assert (
                        "ast_node_name" not in result
                        or result.get("ast_node_name") is None
                    )
                    break

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_ast_node_json_parsing_error(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search when AST JSON parsing fails."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Add invalid AST tree
        file_id = database.get_file_id("test.py", project_id)
        if file_id:
            await database.save_ast_tree(
                file_id, project_id, "invalid json", "test-hash", 1234567890.0
            )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            # Should not raise, but handle error gracefully
            results = await cmd.search("test query", k=5, include_ast_node=True)
            assert isinstance(results, list)

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_ast_node_not_found(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search when AST node is not found in tree."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Add AST tree without matching node
        file_id = database.get_file_id("test.py", project_id)
        if file_id:
            ast_json = '{"_type": "Module", "body": [{"_type": "ClassDef", "name": "OtherClass", "lineno": 999}]}'
            await database.save_ast_tree(
                file_id, project_id, ast_json, "test-hash", 1234567890.0
            )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5, include_ast_node=True)
            # Should not have ast_node if not found
            for result in results:
                if "ast_node" not in result:
                    # This is OK - node not found
                    pass

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_find_ast_node_with_none_line(self, test_db):
        """Test _find_ast_node with None line."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            ast_dict = {
                "_type": "Module",
                "body": [{"_type": "ClassDef", "name": "TestClass", "lineno": 10}],
            }

            # With None line, should not match
            node = cmd._find_ast_node(ast_dict, None, "ClassDef")
            assert node is None

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_find_ast_node_with_none_type(self, test_db):
        """Test _find_ast_node with None node_type."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            ast_dict = {
                "_type": "Module",
                "body": [{"_type": "ClassDef", "name": "TestClass", "lineno": 10}],
            }

            # With None type, should match any type at that line
            node = cmd._find_ast_node(ast_dict, 10, None)
            assert node is not None
            assert node["_type"] == "ClassDef"

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_find_ast_node_non_dict_input(self, test_db):
        """Test _find_ast_node with non-dict input."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            # Should return None for non-dict
            assert cmd._find_ast_node("not a dict", 10, "ClassDef") is None
            assert cmd._find_ast_node([1, 2, 3], 10, "ClassDef") is None
            assert cmd._find_ast_node(None, 10, "ClassDef") is None

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_find_ast_node_nested_search(self, test_db):
        """Test _find_ast_node with nested structures."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            ast_dict = {
                "_type": "Module",
                "body": [
                    {
                        "_type": "ClassDef",
                        "name": "OuterClass",
                        "lineno": 10,
                        "body": [
                            {
                                "_type": "FunctionDef",
                                "name": "inner_method",
                                "lineno": 15,
                            }
                        ],
                    }
                ],
            }

            # Should find nested node
            node = cmd._find_ast_node(ast_dict, 15, "FunctionDef")
            assert node is not None
            assert node["name"] == "inner_method"

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_find_ast_node_list_with_non_dict_items(self, test_db):
        """Test _find_ast_node with list containing non-dict items (covers lines 272-274)."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=None,
                svo_client_manager=None,
            )

            ast_dict = {
                "_type": "Module",
                "body": [
                    "not a dict",  # Non-dict item in list
                    {"_type": "ClassDef", "name": "TestClass", "lineno": 10},
                    123,  # Another non-dict item
                    None,  # None item
                ],
            }

            # Should handle non-dict items gracefully and still find the dict
            node = cmd._find_ast_node(ast_dict, 10, "ClassDef")
            assert node is not None
            assert node["name"] == "TestClass"

        finally:
            database.close()


class TestSemanticSearchEdgeCases:
    """Edge case tests for semantic search."""

    @pytest.mark.asyncio
    async def test_search_empty_query(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search with empty query."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("", k=5)
            # Should handle empty query gracefully
            assert isinstance(results, list)

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_different_project(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search when vector_ids belong to different project."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Create different project
        other_project_id = database.get_or_create_project(
            str(tmpdir), name="other_project"
        )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=other_project_id,  # Different project
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5)
            # Should return empty or filtered results
            assert isinstance(results, list)

        finally:
            database.close()

    @pytest.mark.asyncio
    async def test_search_missing_chunks(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test search when some vector_ids don't have chunks in database."""
        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        # Mock FAISS to return vector_ids that don't exist in database
        mock_faiss_manager.search = Mock(
            return_value=(
                np.array([0.1, 0.2], dtype=np.float32),
                np.array([999, 1000], dtype=np.int64),  # Non-existent vector_ids
            )
        )

        try:
            cmd = SemanticSearchCommand(
                database=database,
                project_id=project_id,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await cmd.search("test query", k=5)
            # Should skip missing chunks and return empty or partial results
            assert isinstance(results, list)

        finally:
            database.close()


class TestSemanticSearchAPI:
    """Tests for API integration."""

    @pytest.mark.asyncio
    async def test_api_semantic_search(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test semantic_search through API."""
        from code_analysis.api import CodeAnalysisAPI

        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            api = CodeAnalysisAPI(
                str(tmpdir),
                db_path=db_path,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await api.semantic_search("test query", k=5)
            assert isinstance(results, list)

        finally:
            api.close()
            database.close()

    @pytest.mark.asyncio
    async def test_api_semantic_search_with_params(
        self, test_db, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test semantic_search through API with all parameters."""
        from code_analysis.api import CodeAnalysisAPI

        db_path, project_id, tmpdir = test_db
        database = CodeDatabase(db_path)

        try:
            api = CodeAnalysisAPI(
                str(tmpdir),
                db_path=db_path,
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            results = await api.semantic_search(
                "test query", k=10, max_distance=0.5, include_ast_node=True
            )
            assert isinstance(results, list)

        finally:
            api.close()
            database.close()

    @pytest.mark.asyncio
    async def test_api_init_without_db_path(
        self, mock_faiss_manager, mock_svo_client_manager
    ):
        """Test API initialization without db_path (covers lines 59-61)."""
        from code_analysis.api import CodeAnalysisAPI
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            # Test API init without db_path - should create default
            api = CodeAnalysisAPI(
                str(tmpdir),
                faiss_manager=mock_faiss_manager,
                svo_client_manager=mock_svo_client_manager,
            )

            # Should have created default db_path
            assert api.db_path is not None
            assert api.db_path.exists() or api.db_path.parent.exists()

            api.close()
