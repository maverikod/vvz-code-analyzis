"""
Additional tests for search CLI to achieve 90%+ coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from click.testing import CliRunner

from code_analysis.cli.search_cli import search
from code_analysis.core.database import CodeDatabase


@pytest.fixture
def test_db_with_data():
    """Create test database with comprehensive sample data."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = CodeDatabase(db_path)

        project_id = db.get_or_create_project(str(tmpdir), name="test_project")
        file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

        class_id = db.add_class(file_id, "TestClass", 10, "Test class", [])
        method_id = db.add_method(
            class_id, "test_method", 15, ["self"], "Test method", False, False, False
        )

        db.add_usage(
            file_id=file_id,
            line=20,
            usage_type="method_call",
            target_type="method",
            target_name="test_method",
            target_class="TestClass",
        )

        db.add_code_content(
            file_id=file_id,
            entity_type="method",
            entity_name="test_method",
            content="def test_method(): pass",
            docstring="Test method docstring",
            entity_id=method_id,
        )

        db.close()
        yield db_path, tmpdir


class TestSearchCliCoverage:
    """Additional tests for search CLI coverage."""

    def test_find_usages_missing_db_error(self):
        """Test find-usages with missing database file."""
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "find-usages",
                "--root-dir",
                "/tmp",
                "--db-path",
                "/nonexistent/db.db",
                "test",
            ],
        )

        assert result.exit_code != 0

    def test_fulltext_missing_db_error(self):
        """Test fulltext with missing database file."""
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "fulltext",
                "--root-dir",
                "/tmp",
                "--db-path",
                "/nonexistent/db.db",
                "test",
            ],
        )

        assert result.exit_code != 0

    def test_class_methods_missing_db_error(self):
        """Test class-methods with missing database file."""
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "class-methods",
                "--root-dir",
                "/tmp",
                "--db-path",
                "/nonexistent/db.db",
                "TestClass",
            ],
        )

        assert result.exit_code != 0

    def test_find_classes_missing_db_error(self):
        """Test find-classes with missing database file."""
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "find-classes",
                "--root-dir",
                "/tmp",
                "--db-path",
                "/nonexistent/db.db",
                "Test",
            ],
        )

        assert result.exit_code != 0

    def test_find_usages_with_context(self, test_db_with_data):
        """Test find-usages showing context."""
        db_path, tmpdir = test_db_with_data
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "find-usages",
                "--root-dir",
                str(tmpdir),
                "--db-path",
                str(db_path),
                "test_method",
            ],
        )

        assert result.exit_code == 0

    def test_fulltext_with_docstring_match(self, test_db_with_data):
        """Test fulltext search matching docstring."""
        db_path, tmpdir = test_db_with_data
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "fulltext",
                "--root-dir",
                str(tmpdir),
                "--db-path",
                str(db_path),
                "docstring",
            ],
        )

        assert result.exit_code == 0

    def test_find_classes_all_classes(self, test_db_with_data):
        """Test find-classes without pattern (all classes)."""
        db_path, tmpdir = test_db_with_data
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "find-classes",
                "--root-dir",
                str(tmpdir),
                "--db-path",
                str(db_path),
                "",
            ],
        )

        assert result.exit_code == 0

    def test_class_methods_with_multiple_methods(self, test_db_with_data):
        """Test class-methods with multiple methods."""
        db_path, tmpdir = test_db_with_data

        # Add another method
        db = CodeDatabase(db_path)
        project_id = db.get_or_create_project(str(tmpdir))
        db.get_file_id("test.py", project_id)
        classes = db.search_classes(None, project_id)
        class_id = classes[0]["id"] if classes else None

        if class_id:
            db.add_method(
                class_id, "another_method", 25, ["self"], "Another", False, False, False
            )
        db.close()

        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "class-methods",
                "--root-dir",
                str(tmpdir),
                "--db-path",
                str(db_path),
                "TestClass",
            ],
        )

        assert result.exit_code == 0
