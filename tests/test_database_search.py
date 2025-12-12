"""
Tests for database search functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase


class TestDatabaseUsages:
    """Tests for usage tracking in database."""

    def test_add_usage(self):
        """Test adding usage record."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            # Create project and file first
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            usage_id = db.add_usage(
                file_id=file_id,
                line=10,
                usage_type="method_call",
                target_type="method",
                target_name="test_method",
                target_class="TestClass",
                context="test_context",
            )

            assert usage_id is not None

            # Verify it was added
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM usages WHERE id = ?", (usage_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row["target_name"] == "test_method"
            assert row["target_class"] == "TestClass"
            assert row["line"] == 10

            db.close()

    def test_add_usage_minimal(self):
        """Test adding usage record with minimal fields."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            # Create project and file first
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            usage_id = db.add_usage(
                file_id=file_id,
                line=5,
                usage_type="attribute_access",
                target_type="property",
                target_name="prop",
            )

            assert usage_id is not None

            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM usages WHERE id = ?", (usage_id,))
            row = cursor.fetchone()
            assert row["target_name"] == "prop"
            assert row["target_class"] is None

            db.close()

    def test_find_usages_by_name(self):
        """Test finding usages by name."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            # Add a project and file
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add usages
            db.add_usage(
                file_id=file_id,
                line=10,
                usage_type="method_call",
                target_type="method",
                target_name="test_method",
            )
            db.add_usage(
                file_id=file_id,
                line=20,
                usage_type="method_call",
                target_type="method",
                target_name="test_method",
            )

            # Find usages
            usages = db.find_usages("test_method", project_id)

            assert len(usages) == 2
            assert all(u["target_name"] == "test_method" for u in usages)

            db.close()

    def test_find_usages_by_type(self):
        """Test finding usages filtered by type."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add method usage
            db.add_usage(
                file_id=file_id,
                line=10,
                usage_type="method_call",
                target_type="method",
                target_name="test_method",
            )

            # Add property usage
            db.add_usage(
                file_id=file_id,
                line=15,
                usage_type="attribute_access",
                target_type="property",
                target_name="test_method",  # Same name, different type
            )

            # Find only method usages
            usages = db.find_usages("test_method", project_id, target_type="method")

            assert len(usages) == 1
            assert usages[0]["target_type"] == "method"

            db.close()

    def test_find_usages_by_class(self):
        """Test finding usages filtered by class."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add usages from different classes
            db.add_usage(
                file_id=file_id,
                line=10,
                usage_type="method_call",
                target_type="method",
                target_name="method",
                target_class="ClassA",
            )
            db.add_usage(
                file_id=file_id,
                line=20,
                usage_type="method_call",
                target_type="method",
                target_name="method",
                target_class="ClassB",
            )

            # Find only ClassA usages
            usages = db.find_usages("method", project_id, target_class="ClassA")

            assert len(usages) == 1
            assert usages[0]["target_class"] == "ClassA"

            db.close()

    def test_find_usages_no_results(self):
        """Test finding usages when none exist."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            usages = db.find_usages("nonexistent", project_id)

            assert len(usages) == 0

            db.close()


class TestDatabaseCodeContent:
    """Tests for code content storage and full-text search."""

    def test_add_code_content(self):
        """Test adding code content."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            content_id = db.add_code_content(
                file_id=file_id,
                entity_type="method",
                entity_name="test_method",
                content="def test_method(): pass",
                docstring="Test method",
                entity_id=1,
            )

            assert content_id is not None

            # Verify it was added
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM code_content WHERE id = ?", (content_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row["entity_name"] == "test_method"
            assert row["content"] == "def test_method(): pass"

            # Verify FTS index was updated
            cursor.execute(
                "SELECT * FROM code_content_fts WHERE rowid = ?", (content_id,)
            )
            fts_row = cursor.fetchone()
            assert fts_row is not None

            db.close()

    def test_add_code_content_no_docstring(self):
        """Test adding code content without docstring."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            content_id = db.add_code_content(
                file_id=file_id,
                entity_type="class",
                entity_name="TestClass",
                content="class TestClass: pass",
            )

            assert content_id is not None

            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM code_content WHERE id = ?", (content_id,))
            row = cursor.fetchone()
            assert row["docstring"] is None

            db.close()

    def test_full_text_search(self):
        """Test full-text search."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add content
            db.add_code_content(
                file_id=file_id,
                entity_type="method",
                entity_name="process_data",
                content="def process_data(): return 'data'",
                docstring="Process data and return result",
            )

            db.add_code_content(
                file_id=file_id,
                entity_type="method",
                entity_name="handle_error",
                content="def handle_error(): pass",
                docstring="Handle error cases",
            )

            # Search
            results = db.full_text_search("process data", project_id)

            assert len(results) > 0
            assert any("process_data" in r["entity_name"] for r in results)

            db.close()

    def test_full_text_search_by_type(self):
        """Test full-text search filtered by entity type."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add class content
            db.add_code_content(
                file_id=file_id,
                entity_type="class",
                entity_name="TestClass",
                content="class TestClass: pass",
                docstring="Test class",
            )

            # Add method content
            db.add_code_content(
                file_id=file_id,
                entity_type="method",
                entity_name="test_method",
                content="def test_method(): pass",
                docstring="Test method",
            )

            # Search only classes
            results = db.full_text_search("test", project_id, entity_type="class")

            assert len(results) > 0
            assert all(r["entity_type"] == "class" for r in results)

            db.close()

    def test_full_text_search_limit(self):
        """Test full-text search with limit."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add multiple contents
            for i in range(10):
                db.add_code_content(
                    file_id=file_id,
                    entity_type="method",
                    entity_name=f"method_{i}",
                    content=f"def method_{i}(): pass",
                    docstring="Test method",
                )

            # Search with limit
            results = db.full_text_search("test", project_id, limit=5)

            assert len(results) <= 5

            db.close()

    def test_full_text_search_no_results(self):
        """Test full-text search when no results."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            results = db.full_text_search("nonexistent_query_xyz", project_id)

            assert len(results) == 0

            db.close()

    def test_clear_file_data_includes_usages(self):
        """Test that clear_file_data removes usages."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add usage
            usage_id = db.add_usage(
                file_id=file_id,
                line=10,
                usage_type="method_call",
                target_type="method",
                target_name="test",
            )

            # Add code content
            content_id = db.add_code_content(
                file_id=file_id,
                entity_type="method",
                entity_name="test",
                content="def test(): pass",
            )

            # Clear file data
            db.clear_file_data(file_id)

            # Verify usages are deleted
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM usages WHERE id = ?", (usage_id,))
            assert cursor.fetchone() is None

            # Verify code content is deleted
            cursor.execute("SELECT * FROM code_content WHERE id = ?", (content_id,))
            assert cursor.fetchone() is None

            # Verify FTS index is cleaned
            cursor.execute(
                "SELECT * FROM code_content_fts WHERE rowid = ?", (content_id,)
            )
            assert cursor.fetchone() is None

            db.close()
