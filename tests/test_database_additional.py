"""
Additional tests for database to reach 90%+ coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase


class TestDatabaseAdditional:
    """Additional database tests for coverage."""

    def test_get_file_summary_with_project(self):
        """Test getting file summary with project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            summary = db.get_file_summary("test.py", project_id)
            assert summary is not None
            assert summary["path"] == "test.py"

            db.close()

    def test_get_file_summary_nonexistent(self):
        """Test getting summary for nonexistent file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            summary = db.get_file_summary("nonexistent.py", project_id)

            assert summary is None

            db.close()

    def test_get_statistics_with_data(self):
        """Test getting statistics with data."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Test", [])
            db.add_method(class_id, "method", 15, ["self"], "Method", False, False, False)
            db.add_function(file_id, "func", 20, ["arg"], "Function")
            db.add_issue("files_too_large", "Too large", file_id=file_id)

            stats = db.get_statistics()
            assert stats["total_files"] == 1
            assert stats["total_classes"] == 1
            assert stats["total_methods"] == 1
            assert stats["total_functions"] == 1
            assert stats["total_issues"] == 1

            db.close()

    def test_search_functions_with_project(self):
        """Test searching functions with project filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_function(file_id, "test_func", 10, ["arg"], "Function")

            # Note: search_functions doesn't have project_id parameter yet
            # This test verifies current behavior
            functions = db.search_functions("test")
            assert len(functions) > 0

            db.close()

    def test_add_code_content_fts_update(self):
        """Test that FTS index is updated when adding content."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            content_id = db.add_code_content(
                file_id, "method", "test", "def test(): pass", "Test docstring"
            )

            # Verify FTS index
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM code_content_fts WHERE rowid = ?", (content_id,))
            fts_row = cursor.fetchone()
            assert fts_row is not None
            assert "test" in fts_row["entity_name"].lower() or "test" in fts_row["content"].lower()

            db.close()

    def test_clear_file_data_removes_all(self):
        """Test that clear_file_data removes all related data."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Test", [])
            method_id = db.add_method(class_id, "method", 15, ["self"], "Method", False, False, False)
            function_id = db.add_function(file_id, "func", 20, ["arg"], "Function")
            
            usage_id = db.add_usage(file_id, 25, "method_call", "method", "method")
            content_id = db.add_code_content(file_id, "method", "method", "def method(): pass")
            issue_id = db.add_issue("files_too_large", "Too large", file_id=file_id)

            # Clear file data
            db.clear_file_data(file_id)

            # Verify all data is removed
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
            assert cursor.fetchone() is None

            cursor.execute("SELECT * FROM methods WHERE id = ?", (method_id,))
            assert cursor.fetchone() is None

            cursor.execute("SELECT * FROM functions WHERE id = ?", (function_id,))
            assert cursor.fetchone() is None

            cursor.execute("SELECT * FROM usages WHERE id = ?", (usage_id,))
            assert cursor.fetchone() is None

            cursor.execute("SELECT * FROM code_content WHERE id = ?", (content_id,))
            assert cursor.fetchone() is None

            cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
            assert cursor.fetchone() is None

            db.close()
