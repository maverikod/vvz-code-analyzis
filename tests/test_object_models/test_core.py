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


class TestFile:
    """Test File object model."""

    def test_create_file_minimal(self):
        """Test creating file with minimal required fields."""
        file_obj = File(project_id="proj-1", path="/test/file.py")
        assert file_obj.project_id == "proj-1"
        assert file_obj.path == "/test/file.py"
        assert file_obj.deleted is False

    def test_file_boolean_fields(self):
        """Test file boolean fields conversion."""
        row = {
            "id": 1,
            "project_id": "proj-1",
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
            path="/test/file.py",
            has_docstring=True,
            deleted=True,
        )
        row = file_obj.to_db_row()
        assert row["has_docstring"] == 1
        assert row["deleted"] == 1
