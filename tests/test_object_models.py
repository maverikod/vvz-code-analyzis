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
    Dataset,
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


class TestBaseObject:
    """Test BaseObject functionality."""

    def test_to_dict(self):
        """Test converting object to dictionary."""
        project = Project(id="test-id", root_path="/test/path", name="Test Project")
        result = project.to_dict()
        assert isinstance(result, dict)
        assert result["id"] == "test-id"
        assert result["root_path"] == "/test/path"
        assert result["name"] == "Test Project"

    def test_to_json(self):
        """Test converting object to JSON string."""
        project = Project(id="test-id", root_path="/test/path")
        json_str = project.to_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["id"] == "test-id"
        assert data["root_path"] == "/test/path"

    def test_from_json(self):
        """Test creating object from JSON string."""
        json_str = '{"id": "test-id", "root_path": "/test/path", "name": "Test"}'
        project = Project.from_json(json_str)
        assert project.id == "test-id"
        assert project.root_path == "/test/path"
        assert project.name == "Test"

    def test_parse_json_field(self):
        """Test parsing JSON field."""
        json_str = '["base1", "base2"]'
        result = Project._parse_json_field(json_str, [])
        assert result == ["base1", "base2"]

    def test_parse_json_field_none(self):
        """Test parsing None JSON field."""
        result = Project._parse_json_field(None, [])
        assert result == []

    def test_to_json_field(self):
        """Test converting value to JSON string."""
        value = ["item1", "item2"]
        result = Project._to_json_field(value)
        assert isinstance(result, str)
        assert json.loads(result) == value

    def test_to_json_field_none(self):
        """Test converting None to JSON field."""
        result = Project._to_json_field(None)
        assert result is None


class TestProject:
    """Test Project object model."""

    def test_create_project_minimal(self):
        """Test creating project with minimal required fields."""
        project = Project(id="test-id", root_path="/test/path")
        assert project.id == "test-id"
        assert project.root_path == "/test/path"
        assert project.name is None
        assert project.comment is None

    def test_create_project_full(self):
        """Test creating project with all fields."""
        created = datetime.now()
        project = Project(
            id="test-id",
            root_path="/test/path",
            name="Test Project",
            comment="Test comment",
            watch_dir_id="watch-123",
            created_at=created,
            updated_at=created,
        )
        assert project.id == "test-id"
        assert project.root_path == "/test/path"
        assert project.name == "Test Project"
        assert project.comment == "Test comment"
        assert project.watch_dir_id == "watch-123"
        assert project.created_at == created

    def test_from_dict_minimal(self):
        """Test creating project from dictionary with minimal fields."""
        data = {"id": "test-id", "root_path": "/test/path"}
        project = Project.from_dict(data)
        assert project.id == "test-id"
        assert project.root_path == "/test/path"

    def test_from_dict_missing_id(self):
        """Test creating project without id raises error."""
        data = {"root_path": "/test/path"}
        with pytest.raises(ValueError, match="Project id is required"):
            Project.from_dict(data)

    def test_from_dict_missing_root_path(self):
        """Test creating project without root_path raises error."""
        data = {"id": "test-id"}
        with pytest.raises(ValueError, match="Project root_path is required"):
            Project.from_dict(data)

    def test_from_db_row(self):
        """Test creating project from database row."""
        row = {
            "id": "test-id",
            "root_path": "/test/path",
            "name": "Test",
            "created_at": 2459580.5,  # Julian day
        }
        project = Project.from_db_row(row)
        assert project.id == "test-id"
        assert project.root_path == "/test/path"
        assert project.name == "Test"

    def test_to_db_row(self):
        """Test converting project to database row."""
        project = Project(id="test-id", root_path="/test/path", name="Test")
        row = project.to_db_row()
        assert row["id"] == "test-id"
        assert row["root_path"] == "/test/path"
        assert row["name"] == "Test"
        assert "created_at" not in row or row["created_at"] is None


class TestDataset:
    """Test Dataset object model."""

    def test_create_dataset_minimal(self):
        """Test creating dataset with minimal required fields."""
        dataset = Dataset(id="ds-1", project_id="proj-1", root_path="/test/path")
        assert dataset.id == "ds-1"
        assert dataset.project_id == "proj-1"
        assert dataset.root_path == "/test/path"

    def test_from_dict_missing_fields(self):
        """Test creating dataset with missing required fields."""
        with pytest.raises(ValueError, match="Dataset id is required"):
            Dataset.from_dict({"project_id": "proj-1", "root_path": "/test"})
        with pytest.raises(ValueError, match="Dataset project_id is required"):
            Dataset.from_dict({"id": "ds-1", "root_path": "/test"})
        with pytest.raises(ValueError, match="Dataset root_path is required"):
            Dataset.from_dict({"id": "ds-1", "project_id": "proj-1"})

    def test_to_db_row(self):
        """Test converting dataset to database row."""
        dataset = Dataset(id="ds-1", project_id="proj-1", root_path="/test/path")
        row = dataset.to_db_row()
        assert row["id"] == "ds-1"
        assert row["project_id"] == "proj-1"
        assert row["root_path"] == "/test/path"


class TestFile:
    """Test File object model."""

    def test_create_file_minimal(self):
        """Test creating file with minimal required fields."""
        file_obj = File(project_id="proj-1", dataset_id="ds-1", path="/test/file.py")
        assert file_obj.project_id == "proj-1"
        assert file_obj.dataset_id == "ds-1"
        assert file_obj.path == "/test/file.py"
        assert file_obj.deleted is False

    def test_file_boolean_fields(self):
        """Test file boolean fields conversion."""
        row = {
            "id": 1,
            "project_id": "proj-1",
            "dataset_id": "ds-1",
            "path": "/test/file.py",
            "has_docstring": 1,
            "deleted": 0,
        }
        file_obj = File.from_db_row(row)
        assert file_obj.has_docstring is True
        assert file_obj.deleted is False

    def test_file_to_db_row_boolean(self):
        """Test converting file boolean fields to database format."""
        file_obj = File(
            project_id="proj-1",
            dataset_id="ds-1",
            path="/test/file.py",
            has_docstring=True,
            deleted=True,
        )
        row = file_obj.to_db_row()
        assert row["has_docstring"] == 1
        assert row["deleted"] == 1


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


class TestClass:
    """Test Class object model."""

    def test_create_class(self):
        """Test creating class."""
        cls = Class(file_id=1, name="TestClass", line=10)
        assert cls.file_id == 1
        assert cls.name == "TestClass"
        assert cls.line == 10
        assert cls.bases == []

    def test_get_set_bases(self):
        """Test getting and setting base classes."""
        cls = Class(file_id=1, name="TestClass", line=10)
        bases = ["Base1", "Base2"]
        cls.set_bases(bases)
        assert cls.get_bases() == bases

    def test_from_dict_with_json_bases(self):
        """Test creating class from dict with JSON bases."""
        data = {
            "file_id": 1,
            "name": "TestClass",
            "line": 10,
            "bases": '["Base1", "Base2"]',
        }
        cls = Class.from_dict(data)
        assert cls.get_bases() == ["Base1", "Base2"]

    def test_from_dict_with_list_bases(self):
        """Test creating class from dict with list bases."""
        data = {"file_id": 1, "name": "TestClass", "line": 10, "bases": ["Base1"]}
        cls = Class.from_dict(data)
        assert cls.get_bases() == ["Base1"]


class TestFunction:
    """Test Function object model."""

    def test_create_function(self):
        """Test creating function."""
        func = Function(file_id=1, name="test_func", line=20)
        assert func.file_id == 1
        assert func.name == "test_func"
        assert func.line == 20
        assert func.args == []

    def test_get_set_args(self):
        """Test getting and setting function arguments."""
        func = Function(file_id=1, name="test_func", line=20)
        args = ["arg1", "arg2"]
        func.set_args(args)
        assert func.get_args() == args


class TestMethod:
    """Test Method object model."""

    def test_create_method(self):
        """Test creating method."""
        method = Method(class_id=1, name="test_method", line=30)
        assert method.class_id == 1
        assert method.name == "test_method"
        assert method.line == 30
        assert method.is_abstract is False
        assert method.has_pass is False

    def test_method_boolean_fields(self):
        """Test method boolean fields conversion."""
        row = {
            "class_id": 1,
            "name": "test_method",
            "line": 30,
            "is_abstract": 1,
            "has_pass": 0,
            "has_not_implemented": 1,
        }
        method = Method.from_db_row(row)
        assert method.is_abstract is True
        assert method.has_pass is False
        assert method.has_not_implemented is True

    def test_method_to_db_row_boolean(self):
        """Test converting method boolean fields to database format."""
        method = Method(
            class_id=1, name="test_method", line=30, is_abstract=True, has_pass=True
        )
        row = method.to_db_row()
        assert row["is_abstract"] == 1
        assert row["has_pass"] == 1


class TestImport:
    """Test Import object model."""

    def test_create_import(self):
        """Test creating import."""
        imp = Import(file_id=1, name="os", import_type="import", line=1, module="os")
        assert imp.file_id == 1
        assert imp.name == "os"
        assert imp.import_type == "import"
        assert imp.module == "os"


class TestIssue:
    """Test Issue object model."""

    def test_create_issue(self):
        """Test creating issue."""
        issue = Issue(issue_type="missing_docstring", line=10)
        assert issue.issue_type == "missing_docstring"
        assert issue.line == 10
        assert issue.metadata == {}

    def test_get_set_metadata(self):
        """Test getting and setting metadata."""
        issue = Issue(issue_type="test")
        metadata = {"key": "value"}
        issue.set_metadata(metadata)
        assert issue.get_metadata() == metadata

    def test_from_dict_with_json_metadata(self):
        """Test creating issue from dict with JSON metadata."""
        data = {"issue_type": "test", "metadata": '{"key": "value"}'}
        issue = Issue.from_dict(data)
        assert issue.get_metadata() == {"key": "value"}


class TestUsage:
    """Test Usage object model."""

    def test_create_usage(self):
        """Test creating usage."""
        usage = Usage(
            file_id=1,
            line=5,
            usage_type="call",
            target_type="function",
            target_name="test_func",
        )
        assert usage.file_id == 1
        assert usage.usage_type == "call"
        assert usage.target_name == "test_func"
        assert usage.context == {}

    def test_get_set_context(self):
        """Test getting and setting context."""
        usage = Usage(
            file_id=1,
            line=5,
            usage_type="call",
            target_type="function",
            target_name="x",
        )
        context = {"key": "value"}
        usage.set_context(context)
        assert usage.get_context() == context


class TestCodeDuplicate:
    """Test CodeDuplicate object model."""

    def test_create_code_duplicate(self):
        """Test creating code duplicate."""
        dup = CodeDuplicate(
            project_id="proj-1", duplicate_hash="hash123", similarity=0.95
        )
        assert dup.project_id == "proj-1"
        assert dup.duplicate_hash == "hash123"
        assert dup.similarity == 0.95


class TestMappers:
    """Test mapper functions."""

    def test_object_to_db_row(self):
        """Test converting object to database row."""
        project = Project(id="test-id", root_path="/test/path")
        row = object_to_db_row(project)
        assert isinstance(row, dict)
        assert row["id"] == "test-id"

    def test_db_row_to_object(self):
        """Test converting database row to object."""
        row = {"id": "test-id", "root_path": "/test/path", "name": "Test"}
        project = db_row_to_object(row, Project)
        assert isinstance(project, Project)
        assert project.id == "test-id"

    def test_db_rows_to_objects(self):
        """Test converting multiple database rows to objects."""
        rows = [
            {"id": "id1", "root_path": "/path1"},
            {"id": "id2", "root_path": "/path2"},
        ]
        projects = db_rows_to_objects(rows, Project)
        assert len(projects) == 2
        assert projects[0].id == "id1"
        assert projects[1].id == "id2"

    def test_object_from_table(self):
        """Test creating object from table name."""
        row = {"id": "test-id", "root_path": "/test/path"}
        project = object_from_table(row, "projects")
        assert isinstance(project, Project)
        assert project.id == "test-id"

    def test_object_from_table_unknown(self):
        """Test creating object from unknown table."""
        row = {"id": 1}
        result = object_from_table(row, "unknown_table")
        assert result is None

    def test_objects_from_table(self):
        """Test creating objects from table name."""
        rows = [
            {"id": "id1", "root_path": "/path1"},
            {"id": "id2", "root_path": "/path2"},
        ]
        projects = objects_from_table(rows, "projects")
        assert len(projects) == 2
        assert all(isinstance(p, Project) for p in projects)

    def test_get_object_class_for_table(self):
        """Test getting object class for table name."""
        cls = get_object_class_for_table("projects")
        assert cls == Project
        cls = get_object_class_for_table("files")
        assert cls == File
        cls = get_object_class_for_table("unknown")
        assert cls is None

    def test_get_table_name_for_object(self):
        """Test getting table name for object."""
        project = Project(id="test", root_path="/test")
        table_name = get_table_name_for_object(project)
        assert table_name == "projects"
        file_obj = File(project_id="test", dataset_id="ds", path="/test")
        table_name = get_table_name_for_object(file_obj)
        assert table_name == "files"


class TestXPathFilter:
    """Test XPathFilter object model."""

    def test_create_xpath_filter_minimal(self):
        """Test creating XPathFilter with minimal required fields."""
        filter_obj = XPathFilter(selector="function[name='test']")
        assert filter_obj.selector == "function[name='test']"
        assert filter_obj.node_type is None
        assert filter_obj.name is None

    def test_create_xpath_filter_full(self):
        """Test creating XPathFilter with all fields."""
        filter_obj = XPathFilter(
            selector="class[name='Test']",
            node_type="class",
            name="Test",
            qualname="module.Test",
            start_line=10,
            end_line=20,
        )
        assert filter_obj.selector == "class[name='Test']"
        assert filter_obj.node_type == "class"
        assert filter_obj.name == "Test"
        assert filter_obj.qualname == "module.Test"
        assert filter_obj.start_line == 10
        assert filter_obj.end_line == 20

    def test_xpath_filter_empty_selector(self):
        """Test XPathFilter with empty selector raises error."""
        with pytest.raises(ValueError, match="selector cannot be empty"):
            XPathFilter(selector="")

    def test_xpath_filter_invalid_selector(self):
        """Test XPathFilter with invalid selector raises error."""
        with pytest.raises(ValueError, match="Invalid selector syntax"):
            XPathFilter(selector="invalid[selector")

    def test_xpath_filter_to_dict(self):
        """Test converting XPathFilter to dictionary."""
        filter_obj = XPathFilter(
            selector="function[name='test']",
            node_type="function",
            start_line=5,
        )
        result = filter_obj.to_dict()
        assert result["selector"] == "function[name='test']"
        assert result["node_type"] == "function"
        assert result["start_line"] == 5
        assert "name" not in result
        assert "end_line" not in result

    def test_xpath_filter_from_dict(self):
        """Test creating XPathFilter from dictionary."""
        data = {
            "selector": "class[name='Test']",
            "node_type": "class",
            "qualname": "module.Test",
            "start_line": 10,
            "end_line": 20,
        }
        filter_obj = XPathFilter.from_dict(data)
        assert filter_obj.selector == "class[name='Test']"
        assert filter_obj.node_type == "class"
        assert filter_obj.qualname == "module.Test"
        assert filter_obj.start_line == 10
        assert filter_obj.end_line == 20

    def test_xpath_filter_str(self):
        """Test string representation of XPathFilter."""
        filter_obj = XPathFilter(selector="function[name='test']", start_line=5)
        str_repr = str(filter_obj)
        assert "selector='function[name='test']'" in str_repr
        assert "start_line=5" in str_repr


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
            ASTNode.from_dict({"project_id": "proj-1", "ast_json": "{}", "ast_hash": "h"})
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
            CSTNode.from_dict({"project_id": "proj-1", "cst_code": "code", "cst_hash": "h"})
        with pytest.raises(ValueError, match="CSTNode project_id is required"):
            CSTNode.from_dict({"file_id": 1, "cst_code": "code", "cst_hash": "h"})
        with pytest.raises(ValueError, match="CSTNode cst_code is required"):
            CSTNode.from_dict({"file_id": 1, "project_id": "proj-1", "cst_hash": "h"})
        with pytest.raises(ValueError, match="CSTNode cst_hash is required"):
            CSTNode.from_dict({"file_id": 1, "project_id": "proj-1", "cst_code": "code"})

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
            VectorIndex.from_dict({"project_id": "proj-1", "entity_id": 1, "vector_id": 100, "vector_dim": 384})
        with pytest.raises(ValueError, match="VectorIndex entity_id is required"):
            VectorIndex.from_dict({"project_id": "proj-1", "entity_type": "file", "vector_id": 100, "vector_dim": 384})
        with pytest.raises(ValueError, match="VectorIndex vector_id is required"):
            VectorIndex.from_dict({"project_id": "proj-1", "entity_type": "file", "entity_id": 1, "vector_dim": 384})
        with pytest.raises(ValueError, match="VectorIndex vector_dim is required"):
            VectorIndex.from_dict({"project_id": "proj-1", "entity_type": "file", "entity_id": 1, "vector_id": 100})

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
            CodeChunk.from_dict({"project_id": "proj-1", "chunk_uuid": "u", "chunk_type": "t", "chunk_text": "txt"})
        with pytest.raises(ValueError, match="CodeChunk project_id is required"):
            CodeChunk.from_dict({"file_id": 1, "chunk_uuid": "u", "chunk_type": "t", "chunk_text": "txt"})
        with pytest.raises(ValueError, match="CodeChunk chunk_uuid is required"):
            CodeChunk.from_dict({"file_id": 1, "project_id": "proj-1", "chunk_type": "t", "chunk_text": "txt"})
        with pytest.raises(ValueError, match="CodeChunk chunk_type is required"):
            CodeChunk.from_dict({"file_id": 1, "project_id": "proj-1", "chunk_uuid": "u", "chunk_text": "txt"})
        with pytest.raises(ValueError, match="CodeChunk chunk_text is required"):
            CodeChunk.from_dict({"file_id": 1, "project_id": "proj-1", "chunk_uuid": "u", "chunk_type": "t"})

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
            Usage.from_dict({"line": 5, "usage_type": "call", "target_type": "func", "target_name": "x"})
        with pytest.raises(ValueError, match="Usage line is required"):
            Usage.from_dict({"file_id": 1, "usage_type": "call", "target_type": "func", "target_name": "x"})
        with pytest.raises(ValueError, match="Usage usage_type is required"):
            Usage.from_dict({"file_id": 1, "line": 5, "target_type": "func", "target_name": "x"})
        with pytest.raises(ValueError, match="Usage target_type is required"):
            Usage.from_dict({"file_id": 1, "line": 5, "usage_type": "call", "target_name": "x"})
        with pytest.raises(ValueError, match="Usage target_name is required"):
            Usage.from_dict({"file_id": 1, "line": 5, "usage_type": "call", "target_type": "func"})

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
        with pytest.raises(ValueError, match="CodeDuplicate duplicate_hash is required"):
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
