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
