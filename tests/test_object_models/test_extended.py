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
    XPathFilter,
    db_row_to_object,
    db_rows_to_objects,
    get_object_class_for_table,
    get_table_name_for_object,
    object_from_table,
    object_to_db_row,
    objects_from_table,
)


class TestASTNodeExtended:
    """Test ASTNode extended functionality."""

    def test_ast_node_from_dict(self):
        """Test creating ASTNode from dictionary."""
        data = {
            "file_id": 1,
            "project_id": "proj-1",
            "ast_json": '{"type": "Module"}',
            "ast_hash": "hash123",
        }
        node = ASTNode.from_dict(data)
        assert node.file_id == 1
        assert node.project_id == "proj-1"
        assert node.ast_json == '{"type": "Module"}'
        assert node.ast_hash == "hash123"

    def test_ast_node_from_dict_missing_fields(self):
        """Test creating ASTNode with missing required fields."""
        with pytest.raises(ValueError, match="ASTNode file_id is required"):
            ASTNode.from_dict(
                {"project_id": "proj-1", "ast_json": "{}", "ast_hash": "h"}
            )
        with pytest.raises(ValueError, match="ASTNode project_id is required"):
            ASTNode.from_dict({"file_id": 1, "ast_json": "{}", "ast_hash": "h"})
        with pytest.raises(ValueError, match="ASTNode ast_json is required"):
            ASTNode.from_dict({"file_id": 1, "project_id": "proj-1", "ast_hash": "h"})
        with pytest.raises(ValueError, match="ASTNode ast_hash is required"):
            ASTNode.from_dict({"file_id": 1, "project_id": "proj-1", "ast_json": "{}"})

    def test_ast_node_from_db_row(self):
        """Test creating ASTNode from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "project_id": "proj-1",
            "ast_json": '{"type": "Module"}',
            "ast_hash": "hash123",
            "file_mtime": 2459580.5,
        }
        node = ASTNode.from_db_row(row)
        assert node.id == 1
        assert node.file_id == 1
        assert node.ast_hash == "hash123"

    def test_ast_node_to_db_row(self):
        """Test converting ASTNode to database row."""
        node = ASTNode(
            id=1,
            file_id=1,
            project_id="proj-1",
            ast_json='{"type": "Module"}',
            ast_hash="hash123",
            file_mtime=datetime.now(),
        )
        row = node.to_db_row()
        assert row["id"] == 1
        assert row["file_id"] == 1
        assert row["project_id"] == "proj-1"
        assert row["ast_json"] == '{"type": "Module"}'
        assert row["ast_hash"] == "hash123"
        assert "file_mtime" in row


class TestCSTNodeExtended:
    """Test CSTNode extended functionality."""

    def test_cst_node_from_dict(self):
        """Test creating CSTNode from dictionary."""
        data = {
            "file_id": 1,
            "project_id": "proj-1",
            "cst_code": "def test(): pass",
            "cst_hash": "hash123",
        }
        node = CSTNode.from_dict(data)
        assert node.file_id == 1
        assert node.cst_code == "def test(): pass"
        assert node.cst_hash == "hash123"

    def test_cst_node_from_dict_missing_fields(self):
        """Test creating CSTNode with missing required fields."""
        with pytest.raises(ValueError, match="CSTNode file_id is required"):
            CSTNode.from_dict(
                {"project_id": "proj-1", "cst_code": "code", "cst_hash": "h"}
            )
        with pytest.raises(ValueError, match="CSTNode project_id is required"):
            CSTNode.from_dict({"file_id": 1, "cst_code": "code", "cst_hash": "h"})
        with pytest.raises(ValueError, match="CSTNode cst_code is required"):
            CSTNode.from_dict({"file_id": 1, "project_id": "proj-1", "cst_hash": "h"})
        with pytest.raises(ValueError, match="CSTNode cst_hash is required"):
            CSTNode.from_dict(
                {"file_id": 1, "project_id": "proj-1", "cst_code": "code"}
            )

    def test_cst_node_from_db_row(self):
        """Test creating CSTNode from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "project_id": "proj-1",
            "cst_code": "def test(): pass",
            "cst_hash": "hash123",
        }
        node = CSTNode.from_db_row(row)
        assert node.id == 1
        assert node.file_id == 1
        assert node.cst_hash == "hash123"

    def test_cst_node_to_db_row(self):
        """Test converting CSTNode to database row."""
        node = CSTNode(
            id=1,
            file_id=1,
            project_id="proj-1",
            cst_code="def test(): pass",
            cst_hash="hash123",
            file_mtime=datetime.now(),
        )
        row = node.to_db_row()
        assert row["id"] == 1
        assert row["file_id"] == 1
        assert row["cst_code"] == "def test(): pass"
        assert row["cst_hash"] == "hash123"
        assert "file_mtime" in row


class TestVectorIndexExtended:
    """Test VectorIndex extended functionality."""

    def test_vector_index_from_dict(self):
        """Test creating VectorIndex from dictionary."""
        data = {
            "project_id": "proj-1",
            "entity_type": "file",
            "entity_id": 1,
            "vector_id": 100,
            "vector_dim": 384,
        }
        vec = VectorIndex.from_dict(data)
        assert vec.project_id == "proj-1"
        assert vec.entity_type == "file"
        assert vec.vector_id == 100
        assert vec.vector_dim == 384

    def test_vector_index_from_dict_missing_fields(self):
        """Test creating VectorIndex with missing required fields."""
        with pytest.raises(ValueError, match="VectorIndex entity_type is required"):
            VectorIndex.from_dict(
                {
                    "project_id": "proj-1",
                    "entity_id": 1,
                    "vector_id": 100,
                    "vector_dim": 384,
                }
            )
        with pytest.raises(ValueError, match="VectorIndex entity_id is required"):
            VectorIndex.from_dict(
                {
                    "project_id": "proj-1",
                    "entity_type": "file",
                    "vector_id": 100,
                    "vector_dim": 384,
                }
            )
        with pytest.raises(ValueError, match="VectorIndex vector_id is required"):
            VectorIndex.from_dict(
                {
                    "project_id": "proj-1",
                    "entity_type": "file",
                    "entity_id": 1,
                    "vector_dim": 384,
                }
            )
        with pytest.raises(ValueError, match="VectorIndex vector_dim is required"):
            VectorIndex.from_dict(
                {
                    "project_id": "proj-1",
                    "entity_type": "file",
                    "entity_id": 1,
                    "vector_id": 100,
                }
            )

    def test_vector_index_from_db_row(self):
        """Test creating VectorIndex from database row."""
        row = {
            "id": 1,
            "project_id": "proj-1",
            "entity_type": "file",
            "entity_id": 1,
            "vector_id": 100,
            "vector_dim": 384,
        }
        vec = VectorIndex.from_db_row(row)
        assert vec.id == 1
        assert vec.vector_id == 100

    def test_vector_index_to_db_row(self):
        """Test converting VectorIndex to database row."""
        vec = VectorIndex(
            id=1,
            project_id="proj-1",
            entity_type="file",
            entity_id=1,
            vector_id=100,
            vector_dim=384,
            embedding_model="test-model",
        )
        row = vec.to_db_row()
        assert row["id"] == 1
        assert row["vector_id"] == 100
        assert row["embedding_model"] == "test-model"


class TestCodeChunkExtended:
    """Test CodeChunk extended functionality."""

    def test_code_chunk_from_dict(self):
        """Test creating CodeChunk from dictionary."""
        data = {
            "file_id": 1,
            "project_id": "proj-1",
            "chunk_uuid": "uuid-123",
            "chunk_type": "docstring",
            "chunk_text": "Test docstring",
        }
        chunk = CodeChunk.from_dict(data)
        assert chunk.file_id == 1
        assert chunk.chunk_uuid == "uuid-123"
        assert chunk.chunk_type == "docstring"

    def test_code_chunk_from_dict_missing_fields(self):
        """Test creating CodeChunk with missing required fields."""
        with pytest.raises(ValueError, match="CodeChunk file_id is required"):
            CodeChunk.from_dict(
                {
                    "project_id": "proj-1",
                    "chunk_uuid": "u",
                    "chunk_type": "t",
                    "chunk_text": "txt",
                }
            )
        with pytest.raises(ValueError, match="CodeChunk project_id is required"):
            CodeChunk.from_dict(
                {
                    "file_id": 1,
                    "chunk_uuid": "u",
                    "chunk_type": "t",
                    "chunk_text": "txt",
                }
            )
        with pytest.raises(ValueError, match="CodeChunk chunk_uuid is required"):
            CodeChunk.from_dict(
                {
                    "file_id": 1,
                    "project_id": "proj-1",
                    "chunk_type": "t",
                    "chunk_text": "txt",
                }
            )
        with pytest.raises(ValueError, match="CodeChunk chunk_type is required"):
            CodeChunk.from_dict(
                {
                    "file_id": 1,
                    "project_id": "proj-1",
                    "chunk_uuid": "u",
                    "chunk_text": "txt",
                }
            )
        with pytest.raises(ValueError, match="CodeChunk chunk_text is required"):
            CodeChunk.from_dict(
                {
                    "file_id": 1,
                    "project_id": "proj-1",
                    "chunk_uuid": "u",
                    "chunk_type": "t",
                }
            )

    def test_code_chunk_from_db_row(self):
        """Test creating CodeChunk from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "project_id": "proj-1",
            "chunk_uuid": "uuid-123",
            "chunk_type": "docstring",
            "chunk_text": "Test",
            "binding_level": 1,
        }
        chunk = CodeChunk.from_db_row(row)
        assert chunk.id == 1
        assert chunk.binding_level == 1

    def test_code_chunk_to_db_row(self):
        """Test converting CodeChunk to database row."""
        chunk = CodeChunk(
            id=1,
            file_id=1,
            project_id="proj-1",
            chunk_uuid="uuid-123",
            chunk_type="docstring",
            chunk_text="Test",
            chunk_ordinal=5,
            vector_id=100,
            line=10,
        )
        row = chunk.to_db_row()
        assert row["id"] == 1
        assert row["chunk_ordinal"] == 5
        assert row["vector_id"] == 100
        assert row["line"] == 10

    def test_code_chunk_set_embedding_vector_none(self):
        """Test setting None embedding vector."""
        chunk = CodeChunk(
            file_id=1,
            project_id="proj-1",
            chunk_uuid="uuid-123",
            chunk_type="docstring",
            chunk_text="Test",
        )
        chunk.set_embedding_vector(None)
        assert chunk.embedding_vector is None


class TestClassExtended:
    """Test Class extended functionality."""

    def test_class_from_dict_missing_fields(self):
        """Test creating Class with missing required fields."""
        with pytest.raises(ValueError, match="Class file_id is required"):
            Class.from_dict({"name": "Test", "line": 10})
        with pytest.raises(ValueError, match="Class name is required"):
            Class.from_dict({"file_id": 1, "line": 10})
        with pytest.raises(ValueError, match="Class line is required"):
            Class.from_dict({"file_id": 1, "name": "Test"})

    def test_class_from_db_row(self):
        """Test creating Class from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "name": "TestClass",
            "line": 10,
            "bases": '["Base1"]',
            "created_at": 2459580.5,
        }
        cls = Class.from_db_row(row)
        assert cls.id == 1
        assert cls.get_bases() == ["Base1"]

    def test_class_to_db_row(self):
        """Test converting Class to database row."""
        cls = Class(
            id=1,
            file_id=1,
            name="TestClass",
            line=10,
            docstring="Test docstring",
            bases=["Base1", "Base2"],
        )
        row = cls.to_db_row()
        assert row["id"] == 1
        assert row["docstring"] == "Test docstring"
        assert "bases" in row
        bases = json.loads(row["bases"])
        assert bases == ["Base1", "Base2"]


class TestFunctionExtended:
    """Test Function extended functionality."""

    def test_function_from_dict_missing_fields(self):
        """Test creating Function with missing required fields."""
        with pytest.raises(ValueError, match="Function file_id is required"):
            Function.from_dict({"name": "test", "line": 10})
        with pytest.raises(ValueError, match="Function name is required"):
            Function.from_dict({"file_id": 1, "line": 10})
        with pytest.raises(ValueError, match="Function line is required"):
            Function.from_dict({"file_id": 1, "name": "test"})

    def test_function_from_dict_with_json_args(self):
        """Test creating function from dict with JSON args."""
        data = {
            "file_id": 1,
            "name": "test_func",
            "line": 10,
            "args": '["arg1", "arg2"]',
        }
        func = Function.from_dict(data)
        assert func.get_args() == ["arg1", "arg2"]

    def test_function_from_db_row(self):
        """Test creating Function from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "name": "test_func",
            "line": 10,
            "args": '["arg1"]',
        }
        func = Function.from_db_row(row)
        assert func.id == 1
        assert func.get_args() == ["arg1"]

    def test_function_to_db_row(self):
        """Test converting Function to database row."""
        func = Function(
            id=1,
            file_id=1,
            name="test_func",
            line=10,
            args=["arg1", "arg2"],
            docstring="Test docstring",
        )
        row = func.to_db_row()
        assert row["id"] == 1
        assert row["docstring"] == "Test docstring"
        assert "args" in row
        args = json.loads(row["args"])
        assert args == ["arg1", "arg2"]


class TestMethodExtended:
    """Test Method extended functionality."""

    def test_method_from_dict_missing_fields(self):
        """Test creating Method with missing required fields."""
        with pytest.raises(ValueError, match="Method class_id is required"):
            Method.from_dict({"name": "test", "line": 10})
        with pytest.raises(ValueError, match="Method name is required"):
            Method.from_dict({"class_id": 1, "line": 10})
        with pytest.raises(ValueError, match="Method line is required"):
            Method.from_dict({"class_id": 1, "name": "test"})

    def test_method_from_dict_with_json_args(self):
        """Test creating method from dict with JSON args."""
        data = {
            "class_id": 1,
            "name": "test_method",
            "line": 10,
            "args": '["self", "arg1"]',
        }
        method = Method.from_dict(data)
        assert method.get_args() == ["self", "arg1"]

    def test_method_from_db_row_with_none_booleans(self):
        """Test creating method from db row with None boolean values."""
        row = {
            "class_id": 1,
            "name": "test_method",
            "line": 10,
            "is_abstract": None,
            "has_pass": None,
            "has_not_implemented": None,
        }
        method = Method.from_db_row(row)
        assert method.is_abstract is False
        assert method.has_pass is False

    def test_method_to_db_row(self):
        """Test converting Method to database row."""
        method = Method(
            id=1,
            class_id=1,
            name="test_method",
            line=10,
            args=["self", "arg1"],
            docstring="Test docstring",
            is_abstract=True,
            has_not_implemented=True,
        )
        row = method.to_db_row()
        assert row["id"] == 1
        assert row["is_abstract"] == 1
        assert row["has_not_implemented"] == 1
        assert row["has_pass"] == 0


class TestImportExtended:
    """Test Import extended functionality."""

    def test_import_from_dict_missing_fields(self):
        """Test creating Import with missing required fields."""
        with pytest.raises(ValueError, match="Import file_id is required"):
            Import.from_dict({"name": "os", "import_type": "import", "line": 1})
        with pytest.raises(ValueError, match="Import name is required"):
            Import.from_dict({"file_id": 1, "import_type": "import", "line": 1})
        with pytest.raises(ValueError, match="Import import_type is required"):
            Import.from_dict({"file_id": 1, "name": "os", "line": 1})
        with pytest.raises(ValueError, match="Import line is required"):
            Import.from_dict({"file_id": 1, "name": "os", "import_type": "import"})

    def test_import_from_db_row(self):
        """Test creating Import from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "name": "os",
            "import_type": "import",
            "line": 1,
            "module": "os",
        }
        imp = Import.from_db_row(row)
        assert imp.id == 1
        assert imp.module == "os"

    def test_import_to_db_row(self):
        """Test converting Import to database row."""
        imp = Import(
            id=1,
            file_id=1,
            name="os",
            import_type="import",
            line=1,
            module="os",
        )
        row = imp.to_db_row()
        assert row["id"] == 1
        assert row["module"] == "os"
        assert "created_at" not in row or row.get("created_at") is None


class TestIssueExtended:
    """Test Issue extended functionality."""

    def test_issue_from_dict_missing_issue_type(self):
        """Test creating Issue without issue_type raises error."""
        with pytest.raises(ValueError, match="Issue issue_type is required"):
            Issue.from_dict({"line": 10})

    def test_issue_from_dict_with_json_metadata(self):
        """Test creating issue from dict with JSON metadata."""
        data = {"issue_type": "test", "metadata": '{"key": "value"}'}
        issue = Issue.from_dict(data)
        assert issue.get_metadata() == {"key": "value"}

    def test_issue_from_dict_with_dict_metadata(self):
        """Test creating issue from dict with dict metadata."""
        data = {"issue_type": "test", "metadata": {"key": "value"}}
        issue = Issue.from_dict(data)
        assert issue.get_metadata() == {"key": "value"}

    def test_issue_from_db_row(self):
        """Test creating Issue from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "project_id": "proj-1",
            "issue_type": "missing_docstring",
            "line": 10,
            "description": "Test issue",
            "metadata": '{"key": "value"}',
        }
        issue = Issue.from_db_row(row)
        assert issue.id == 1
        assert issue.issue_type == "missing_docstring"
        assert issue.get_metadata() == {"key": "value"}

    def test_issue_to_db_row(self):
        """Test converting Issue to database row."""
        issue = Issue(
            id=1,
            file_id=1,
            project_id="proj-1",
            issue_type="missing_docstring",
            line=10,
            description="Test",
            metadata={"key": "value"},
        )
        row = issue.to_db_row()
        assert row["id"] == 1
        assert row["file_id"] == 1
        assert row["description"] == "Test"
        assert "metadata" in row


class TestUsageExtended:
    """Test Usage extended functionality."""

    def test_usage_from_dict_missing_fields(self):
        """Test creating Usage with missing required fields."""
        with pytest.raises(ValueError, match="Usage file_id is required"):
            Usage.from_dict(
                {
                    "line": 5,
                    "usage_type": "call",
                    "target_type": "func",
                    "target_name": "x",
                }
            )
        with pytest.raises(ValueError, match="Usage line is required"):
            Usage.from_dict(
                {
                    "file_id": 1,
                    "usage_type": "call",
                    "target_type": "func",
                    "target_name": "x",
                }
            )
        with pytest.raises(ValueError, match="Usage usage_type is required"):
            Usage.from_dict(
                {"file_id": 1, "line": 5, "target_type": "func", "target_name": "x"}
            )
        with pytest.raises(ValueError, match="Usage target_type is required"):
            Usage.from_dict(
                {"file_id": 1, "line": 5, "usage_type": "call", "target_name": "x"}
            )
        with pytest.raises(ValueError, match="Usage target_name is required"):
            Usage.from_dict(
                {"file_id": 1, "line": 5, "usage_type": "call", "target_type": "func"}
            )

    def test_usage_from_dict_with_json_context(self):
        """Test creating usage from dict with JSON context."""
        data = {
            "file_id": 1,
            "line": 5,
            "usage_type": "call",
            "target_type": "function",
            "target_name": "test",
            "context": '{"key": "value"}',
        }
        usage = Usage.from_dict(data)
        assert usage.get_context() == {"key": "value"}

    def test_usage_from_db_row(self):
        """Test creating Usage from database row."""
        row = {
            "id": 1,
            "file_id": 1,
            "line": 5,
            "usage_type": "call",
            "target_type": "function",
            "target_name": "test",
            "context": '{"key": "value"}',
        }
        usage = Usage.from_db_row(row)
        assert usage.id == 1
        assert usage.get_context() == {"key": "value"}

    def test_usage_to_db_row(self):
        """Test converting Usage to database row."""
        usage = Usage(
            id=1,
            file_id=1,
            line=5,
            usage_type="call",
            target_type="function",
            target_name="test",
            target_class="TestClass",
            context={"key": "value"},
        )
        row = usage.to_db_row()
        assert row["id"] == 1
        assert row["target_class"] == "TestClass"
        assert "context" in row


class TestCodeDuplicateExtended:
    """Test CodeDuplicate extended functionality."""

    def test_code_duplicate_from_dict_missing_fields(self):
        """Test creating CodeDuplicate with missing required fields."""
        with pytest.raises(ValueError, match="CodeDuplicate project_id is required"):
            CodeDuplicate.from_dict({"duplicate_hash": "h", "similarity": 0.9})
        with pytest.raises(
            ValueError, match="CodeDuplicate duplicate_hash is required"
        ):
            CodeDuplicate.from_dict({"project_id": "proj-1", "similarity": 0.9})
        with pytest.raises(ValueError, match="CodeDuplicate similarity is required"):
            CodeDuplicate.from_dict({"project_id": "proj-1", "duplicate_hash": "h"})

    def test_code_duplicate_from_db_row(self):
        """Test creating CodeDuplicate from database row."""
        row = {
            "id": 1,
            "project_id": "proj-1",
            "duplicate_hash": "hash123",
            "similarity": 0.95,
            "created_at": 2459580.5,
        }
        dup = CodeDuplicate.from_db_row(row)
        assert dup.id == 1
        assert dup.similarity == 0.95

    def test_code_duplicate_to_db_row(self):
        """Test converting CodeDuplicate to database row."""
        dup = CodeDuplicate(
            id=1,
            project_id="proj-1",
            duplicate_hash="hash123",
            similarity=0.95,
            created_at=datetime.now(),
        )
        row = dup.to_db_row()
        assert row["id"] == 1
        assert row["similarity"] == 0.95
        assert "created_at" in row
