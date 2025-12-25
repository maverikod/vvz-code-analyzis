"""
Additional tests for database to achieve 90%+ coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase


class TestDatabaseProjectManagement:
    """Tests for project management in database."""

    def test_get_or_create_project_new(self):
        """Test creating new project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project("/test/project", name="TestProject")

            assert project_id is not None

            # Verify it was created
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row["root_path"] == "/test/project"
            assert row["name"] == "TestProject"

            db.close()

    def test_get_or_create_project_existing(self):
        """Test getting existing project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id1 = db.get_or_create_project("/test/project", name="TestProject")
            project_id2 = db.get_or_create_project("/test/project", name="TestProject2")

            assert project_id1 == project_id2
            # Name should not change
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id1,))
            row = cursor.fetchone()
            assert row["name"] == "TestProject"  # First name is kept

            db.close()

    def test_get_or_create_project_default_name(self):
        """Test creating project with default name."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project("/test/my_project")

            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            assert row["name"] == "my_project"

            db.close()

    def test_get_project_id_existing(self):
        """Test getting existing project ID."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project("/test/project")
            found_id = db.get_project_id("/test/project")

            assert found_id == project_id

            db.close()

    def test_get_project_id_nonexistent(self):
        """Test getting nonexistent project ID."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            found_id = db.get_project_id("/nonexistent/project")

            assert found_id is None

            db.close()

    def test_add_file_with_project(self):
        """Test adding file with project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            assert file_id is not None

            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
            row = cursor.fetchone()
            assert row["project_id"] == project_id

            db.close()

    def test_get_file_id_with_project(self):
        """Test getting file ID with project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            found_id = db.get_file_id("test.py", project_id)
            assert found_id == file_id

            # Different project should not find it
            project_id2 = db.get_or_create_project("/other/project")
            found_id2 = db.get_file_id("test.py", project_id2)
            assert found_id2 is None

            db.close()

    def test_search_classes_with_project_id(self):
        """Test searching classes with project filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id1 = db.get_or_create_project(str(tmpdir), name="project1")
            project_id2 = db.get_or_create_project("/other/project", name="project2")

            file_id1 = db.add_file("file1.py", 100, 1234567890.0, True, project_id1)
            file_id2 = db.add_file("file2.py", 100, 1234567890.0, True, project_id2)

            class_id1 = db.add_class(file_id1, "ClassA", 10, "Class A", [])
            db.add_class(file_id2, "ClassA", 10, "Class A", [])

            # Search in project1
            classes = db.search_classes("ClassA", project_id=project_id1)
            assert len(classes) == 1
            assert classes[0]["id"] == class_id1

            db.close()

    def test_search_methods_with_project_id(self):
        """Test searching methods with project filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id1 = db.get_or_create_project(str(tmpdir), name="project1")
            project_id2 = db.get_or_create_project("/other/project", name="project2")

            file_id1 = db.add_file("file1.py", 100, 1234567890.0, True, project_id1)
            file_id2 = db.add_file("file2.py", 100, 1234567890.0, True, project_id2)

            class_id1 = db.add_class(file_id1, "ClassA", 10, "Class A", [])
            class_id2 = db.add_class(file_id2, "ClassB", 10, "Class B", [])

            method_id1 = db.add_method(
                class_id1, "method", 15, ["self"], "Method", False, False, False
            )
            db.add_method(
                class_id2, "method", 15, ["self"], "Method", False, False, False
            )

            # Search in project1
            methods = db.search_methods("method", project_id=project_id1)
            assert len(methods) == 1
            assert methods[0]["id"] == method_id1

            db.close()

    def test_get_issues_by_type_with_project(self):
        """Test getting issues filtered by project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id1 = db.get_or_create_project(str(tmpdir), name="project1")
            project_id2 = db.get_or_create_project("/other/project", name="project2")

            file_id1 = db.add_file("file1.py", 100, 1234567890.0, False, project_id1)
            file_id2 = db.add_file("file2.py", 100, 1234567890.0, False, project_id2)

            db.add_issue(
                "files_without_docstrings", "Missing docstring", file_id=file_id1
            )
            db.add_issue(
                "files_without_docstrings", "Missing docstring", file_id=file_id2
            )

            # Get issues for project1
            issues = db.get_issues_by_type(
                "files_without_docstrings", project_id=project_id1
            )
            assert len(issues) == 1
            assert issues[0]["file_id"] == file_id1

            db.close()

    def test_full_text_search_with_project(self):
        """Test full-text search filtered by project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id1 = db.get_or_create_project(str(tmpdir), name="project1")
            project_id2 = db.get_or_create_project("/other/project", name="project2")

            file_id1 = db.add_file("file1.py", 100, 1234567890.0, True, project_id1)
            file_id2 = db.add_file("file2.py", 100, 1234567890.0, True, project_id2)

            db.add_code_content(
                file_id1, "method", "test_method", "def test_method(): pass", "Test"
            )
            db.add_code_content(
                file_id2, "method", "test_method", "def test_method(): pass", "Test"
            )

            # Search in project1
            results = db.full_text_search("test", project_id1, limit=10)
            assert len(results) == 1
            assert results[0]["file_id"] == file_id1

            db.close()

    def test_find_usages_with_project(self):
        """Test finding usages filtered by project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = CodeDatabase(db_path)

            project_id1 = db.get_or_create_project(str(tmpdir), name="project1")
            project_id2 = db.get_or_create_project("/other/project", name="project2")

            file_id1 = db.add_file("file1.py", 100, 1234567890.0, True, project_id1)
            file_id2 = db.add_file("file2.py", 100, 1234567890.0, True, project_id2)

            db.add_usage(file_id1, 10, "method_call", "method", "test_method")
            db.add_usage(file_id2, 20, "method_call", "method", "test_method")

            # Find usages in project1
            usages = db.find_usages("test_method", project_id1)
            assert len(usages) == 1
            assert usages[0]["file_id"] == file_id1

            db.close()
