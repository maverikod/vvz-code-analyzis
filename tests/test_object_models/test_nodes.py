"""
Unit tests for database object models.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from datetime import datetime

import pytest

from code_analysis.core.database_client.objects import (
    ASTNode,
    Class,
    CodeChunk,
    CodeDuplicate,
    CSTNode,
    File,
    Function,
    Import,
    Issue,
    Method,
    Project,
    Usage,
    VectorIndex,
    db_row_to_object,
    db_rows_to_objects,
    get_object_class_for_table,
    get_table_name_for_object,
    object_from_table,
    object_to_db_row,
    objects_from_table,
)


class TestASTNode:
    """Test ASTNode object model."""

    def test_create_ast_node(self):
        """Test creating AST node."""
        ast_data = {"type": "Module", "body": []}
        ast_json = json.dumps(ast_data)
        node = ASTNode(
            file_id=1,
            project_id="proj-1",
            ast_json=ast_json,
            ast_hash="hash123",
        )
        assert node.file_id == 1
        assert node.project_id == "proj-1"
        assert node.ast_hash == "hash123"

    def test_get_set_ast_data(self):
        """Test getting and setting AST data."""
        node = ASTNode(file_id=1, project_id="proj-1", ast_json="", ast_hash="hash")
        ast_data = {"type": "Module", "body": []}
        node.set_ast_data(ast_data)
        result = node.get_ast_data()
        assert result == ast_data


class TestCSTNode:
    """Test CSTNode object model."""

    def test_create_cst_node(self):
        """Test creating CST node."""
        node = CSTNode(
            file_id=1,
            project_id="proj-1",
            cst_code="def test(): pass",
            cst_hash="hash123",
        )
        assert node.file_id == 1
        assert node.cst_code == "def test(): pass"
        assert node.cst_hash == "hash123"


class TestVectorIndex:
    """Test VectorIndex object model."""

    def test_create_vector_index(self):
        """Test creating vector index."""
        vec = VectorIndex(
            project_id="proj-1",
            entity_type="file",
            entity_id=1,
            vector_id=100,
            vector_dim=384,
        )
        assert vec.project_id == "proj-1"
        assert vec.entity_type == "file"
        assert vec.entity_id == 1
        assert vec.vector_id == 100
        assert vec.vector_dim == 384

    def test_from_dict_missing_fields(self):
        """Test creating vector index with missing required fields."""
        with pytest.raises(ValueError, match="VectorIndex project_id is required"):
            VectorIndex.from_dict({"entity_type": "file", "entity_id": 1})


class TestCodeChunk:
    """Test CodeChunk object model."""

    def test_create_code_chunk(self):
        """Test creating code chunk."""
        chunk = CodeChunk(
            file_id=1,
            project_id="proj-1",
            chunk_uuid="uuid-123",
            chunk_type="docstring",
            chunk_text="Test docstring",
        )
        assert chunk.file_id == 1
        assert chunk.chunk_uuid == "uuid-123"
        assert chunk.chunk_type == "docstring"
        assert chunk.binding_level == 0

    def test_get_set_embedding_vector(self):
        """Test getting and setting embedding vector."""
        chunk = CodeChunk(
            file_id=1,
            project_id="proj-1",
            chunk_uuid="uuid-123",
            chunk_type="docstring",
            chunk_text="Test",
        )
        vector = [0.1, 0.2, 0.3]
        chunk.set_embedding_vector(vector)
        result = chunk.get_embedding_vector()
        assert result == vector

    def test_get_embedding_vector_none(self):
        """Test getting None embedding vector."""
        chunk = CodeChunk(
            file_id=1,
            project_id="proj-1",
            chunk_uuid="uuid-123",
            chunk_type="docstring",
            chunk_text="Test",
        )
        assert chunk.get_embedding_vector() is None
