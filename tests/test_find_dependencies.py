"""
Tests for find_dependencies command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.find_dependencies import FindDependenciesCommand


class TestFindDependencies:
    """Tests for FindDependenciesCommand."""

    @pytest.mark.asyncio
    async def test_find_dependencies_empty(self):
        """Test finding dependencies in empty project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            cmd = FindDependenciesCommand(db, project_id, "TestClass")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 0
            assert len(result["dependencies"]) == 0

            db.close()

    @pytest.mark.asyncio
    async def test_find_dependencies_in_usages(self):
        """Test finding dependencies in usages table."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add files
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)

            # Add usages
            db.add_usage(
                file1_id,
                10,
                "method_call",
                "method",
                "test_method",
                "TestClass",
                "context1",
            )
            db.add_usage(
                file2_id,
                20,
                "method_call",
                "method",
                "test_method",
                "TestClass",
                "context2",
            )
            db.add_usage(
                file1_id,
                15,
                "attribute_access",
                "property",
                "test_prop",
                "TestClass",
                "context3",
            )

            # Find dependencies for test_method
            cmd = FindDependenciesCommand(
                db, project_id, "test_method", entity_type="method"
            )
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 2
            assert len(result["dependencies"]) == 2

            # Check that both files are in results
            file_paths = {dep["file_path"] for dep in result["dependencies"]}
            assert "file1.py" in file_paths
            assert "file2.py" in file_paths

            db.close()

    @pytest.mark.asyncio
    async def test_find_dependencies_in_imports(self):
        """Test finding dependencies in imports table."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add files
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)

            # Add imports
            db.add_import(file1_id, "os", None, "import", 1)
            db.add_import(file2_id, "sys", None, "import", 1)
            db.add_import(file1_id, "Path", "pathlib", "import_from", 2)

            # Find dependencies for pathlib module
            cmd = FindDependenciesCommand(
                db, project_id, "pathlib", entity_type="module"
            )
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] >= 1
            # Should find file1.py which imports from pathlib
            file_paths = {dep["file_path"] for dep in result["dependencies"]}
            assert "file1.py" in file_paths

            db.close()

    @pytest.mark.asyncio
    async def test_find_dependencies_with_target_class(self):
        """Test finding dependencies with target class filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add usages with different target classes
            db.add_usage(
                file_id,
                10,
                "method_call",
                "method",
                "test_method",
                "Class1",
                "context1",
            )
            db.add_usage(
                file_id,
                20,
                "method_call",
                "method",
                "test_method",
                "Class2",
                "context2",
            )

            # Find dependencies for test_method in Class1 only
            cmd = FindDependenciesCommand(
                db,
                project_id,
                "test_method",
                entity_type="method",
                target_class="Class1",
            )
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 1
            assert len(result["dependencies"]) == 1
            assert result["dependencies"][0]["usages"][0]["line"] == 10

            db.close()

    @pytest.mark.asyncio
    async def test_find_dependencies_all_types(self):
        """Test finding dependencies for all types."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add usage
            db.add_usage(
                file_id,
                10,
                "method_call",
                "method",
                "test_entity",
                "TestClass",
                "context1",
            )
            # Add import
            db.add_import(file_id, "test_entity", None, "import", 5)

            # Find dependencies for test_entity (all types)
            cmd = FindDependenciesCommand(db, project_id, "test_entity")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] >= 1
            # Should find both usage and import

            db.close()

    @pytest.mark.asyncio
    async def test_find_dependencies_with_limit(self):
        """Test finding dependencies with limit."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add multiple usages
            for i in range(10):
                db.add_usage(
                    file_id,
                    10 + i,
                    "method_call",
                    "method",
                    "test_method",
                    "TestClass",
                    f"context{i}",
                )

            # Get first 5
            cmd = FindDependenciesCommand(db, project_id, "test_method", limit=5)
            result = await cmd.execute()

            assert result["success"] is True
            # Should have at least 5 results (may be more if grouped by file)
            assert result["limit"] == 5

            db.close()

    @pytest.mark.asyncio
    async def test_find_dependencies_grouped_by_file(self):
        """Test that dependencies are grouped by file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            # Add multiple usages in same file
            db.add_usage(
                file_id,
                10,
                "method_call",
                "method",
                "test_method",
                "TestClass",
                "context1",
            )
            db.add_usage(
                file_id,
                20,
                "method_call",
                "method",
                "test_method",
                "TestClass",
                "context2",
            )
            db.add_usage(
                file_id,
                30,
                "method_call",
                "method",
                "test_method",
                "TestClass",
                "context3",
            )

            cmd = FindDependenciesCommand(db, project_id, "test_method")
            result = await cmd.execute()

            assert result["success"] is True
            assert len(result["dependencies"]) == 1
            assert result["dependencies"][0]["file_path"] == "test.py"
            assert len(result["dependencies"][0]["usages"]) == 3

            db.close()
