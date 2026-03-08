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
