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
        file_obj = File(project_id="test", path="/test")
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
