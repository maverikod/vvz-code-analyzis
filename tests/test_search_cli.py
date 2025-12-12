"""
Tests for search CLI commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from click.testing import CliRunner

from code_analysis.cli.search_cli import search
from code_analysis.core.database import CodeDatabase


@pytest.fixture
def test_db():
    """Create test database with sample data."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = CodeDatabase(db_path)

        # Add project first
        project_id = db.get_or_create_project(str(tmpdir), name="test_project")

        # Add file
        file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

        # Add class
        class_id = db.add_class(file_id, "TestClass", 10, "Test class", [])

        # Add method
        method_id = db.add_method(
            class_id, "test_method", 15, ["self"], "Test method", False, False, False
        )

        # Add usage
        db.add_usage(
            file_id=file_id,
            line=20,
            usage_type="method_call",
            target_type="method",
            target_name="test_method",
            target_class="TestClass",
        )

        # Add code content
        db.add_code_content(
            file_id=file_id,
            entity_type="method",
            entity_name="test_method",
            content="def test_method(): pass",
            docstring="Test method docstring",
            entity_id=method_id,
        )

        db.close()
        yield db_path


class TestFindUsagesCommand:
    """Tests for find-usages command."""

    def test_find_usages_basic(self, test_db):
        """Test basic find-usages command."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["find-usages", "--root-dir", str(root_dir), "--db-path", str(test_db), "test_method"]
        )

        assert result.exit_code == 0
        assert "test_method" in result.output
        assert "test.py" in result.output

    def test_find_usages_with_type(self, test_db):
        """Test find-usages with type filter."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "find-usages",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "test_method",
                "--type",
                "method",
            ],
        )

        assert result.exit_code == 0
        assert "test_method" in result.output

    def test_find_usages_with_class(self, test_db):
        """Test find-usages with class filter."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "find-usages",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "test_method",
                "--class",
                "TestClass",
            ],
        )

        assert result.exit_code == 0
        assert "test_method" in result.output

    def test_find_usages_json_format(self, test_db):
        """Test find-usages with JSON format."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "find-usages",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "test_method",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_find_usages_no_results(self, test_db):
        """Test find-usages when no results."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["find-usages", "--root-dir", str(root_dir), "--db-path", str(test_db), "nonexistent"]
        )

        assert result.exit_code == 0
        assert "No usages found" in result.output

    def test_find_usages_missing_db(self):
        """Test find-usages with missing database."""
        runner = CliRunner()
        result = runner.invoke(
            search,
            [
                "find-usages",
                "--db-path",
                "/nonexistent.db",
                "test_method",
            ],
        )

        assert result.exit_code != 0


class TestFulltextCommand:
    """Tests for fulltext command."""

    def test_fulltext_basic(self, test_db):
        """Test basic fulltext command."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["fulltext", "--root-dir", str(root_dir), "--db-path", str(test_db), "test"]
        )

        assert result.exit_code == 0
        assert "result" in result.output.lower()

    def test_fulltext_with_type(self, test_db):
        """Test fulltext with type filter."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "fulltext",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "test",
                "--type",
                "method",
            ],
        )

        assert result.exit_code == 0

    def test_fulltext_with_limit(self, test_db):
        """Test fulltext with limit."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "fulltext",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "test",
                "--limit",
                "5",
            ],
        )

        assert result.exit_code == 0

    def test_fulltext_json_format(self, test_db):
        """Test fulltext with JSON format."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "fulltext",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "test",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_fulltext_no_results(self, test_db):
        """Test fulltext when no results."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            ["fulltext", "--root-dir", str(root_dir), "--db-path", str(test_db), "nonexistent_query_xyz123"],
        )

        assert result.exit_code == 0
        assert "No results found" in result.output


class TestClassMethodsCommand:
    """Tests for class-methods command."""

    def test_class_methods_basic(self, test_db):
        """Test basic class-methods command."""
        runner = CliRunner()
        # Need to provide root-dir
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["class-methods", "--root-dir", str(root_dir), "--db-path", str(test_db), "TestClass"]
        )

        assert result.exit_code == 0
        assert "test_method" in result.output

    def test_class_methods_json_format(self, test_db):
        """Test class-methods with JSON format."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "class-methods",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "TestClass",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_class_methods_no_results(self, test_db):
        """Test class-methods when no results."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["class-methods", "--root-dir", str(root_dir), "--db-path", str(test_db), "NonexistentClass"]
        )

        assert result.exit_code == 0
        assert "No methods found" in result.output


class TestFindClassesCommand:
    """Tests for find-classes command."""

    def test_find_classes_basic(self, test_db):
        """Test basic find-classes command."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["find-classes", "--root-dir", str(root_dir), "--db-path", str(test_db), "Test"]
        )

        assert result.exit_code == 0
        assert "TestClass" in result.output

    def test_find_classes_json_format(self, test_db):
        """Test find-classes with JSON format."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search,
            [
                "find-classes",
                "--root-dir",
                str(root_dir),
                "--db-path",
                str(test_db),
                "Test",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_find_classes_no_results(self, test_db):
        """Test find-classes when no results."""
        runner = CliRunner()
        root_dir = test_db.parent
        result = runner.invoke(
            search, ["find-classes", "--root-dir", str(root_dir), "--db-path", str(test_db), "Nonexistent"]
        )

        assert result.exit_code == 0
        assert "No classes found" in result.output
