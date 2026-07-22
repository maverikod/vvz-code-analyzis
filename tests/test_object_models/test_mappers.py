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
