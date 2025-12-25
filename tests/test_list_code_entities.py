"""
Tests for list_code_entities command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.list_code_entities import ListCodeEntitiesCommand


class TestListCodeEntities:
    """Tests for ListCodeEntitiesCommand."""

    @pytest.mark.asyncio
    async def test_list_classes_empty(self):
        """Test listing classes in empty project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            cmd = ListCodeEntitiesCommand(db, project_id, entity_type="class")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["entity_type"] == "class"
            assert result["total"] == 0
            assert len(result["entities"]) == 0

            db.close()

    @pytest.mark.asyncio
    async def test_list_classes(self):
        """Test listing classes."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add files and classes
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)

            db.add_class(file1_id, "Class1", 10, "Class 1 docstring", ["Base1"])
            db.add_class(file1_id, "Class2", 20, "Class 2 docstring", [])
            db.add_class(
                file2_id, "Class3", 15, "Class 3 docstring", ["Base2", "Base3"]
            )

            cmd = ListCodeEntitiesCommand(db, project_id, entity_type="class")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["entity_type"] == "class"
            assert result["total"] == 3
            assert len(result["entities"]) == 3

            # Check classes are sorted by file_path and line
            classes_by_name = {c["name"]: c for c in result["entities"]}
            assert "Class1" in classes_by_name
            assert "Class2" in classes_by_name
            assert "Class3" in classes_by_name

            assert classes_by_name["Class1"]["bases"] == ["Base1"]
            assert classes_by_name["Class2"]["bases"] == []
            assert classes_by_name["Class3"]["bases"] == ["Base2", "Base3"]

            db.close()

    @pytest.mark.asyncio
    async def test_list_functions(self):
        """Test listing functions."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and functions
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            db.add_function(file_id, "func1", 10, ["arg1"], "Function 1")
            db.add_function(file_id, "func2", 20, ["arg1", "arg2"], "Function 2")

            cmd = ListCodeEntitiesCommand(db, project_id, entity_type="function")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["entity_type"] == "function"
            assert result["total"] == 2
            assert len(result["entities"]) == 2

            functions_by_name = {f["name"]: f for f in result["entities"]}
            assert functions_by_name["func1"]["args"] == ["arg1"]
            assert functions_by_name["func2"]["args"] == ["arg1", "arg2"]

            db.close()

    @pytest.mark.asyncio
    async def test_list_methods(self):
        """Test listing methods."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file, class, and methods
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Class docstring", [])

            db.add_method(class_id, "method1", 15, ["self"], "Method 1")
            db.add_method(
                class_id, "method2", 25, ["self", "arg1"], "Method 2", is_abstract=True
            )

            cmd = ListCodeEntitiesCommand(db, project_id, entity_type="method")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["entity_type"] == "method"
            assert result["total"] == 2
            assert len(result["entities"]) == 2

            methods_by_name = {m["name"]: m for m in result["entities"]}
            assert methods_by_name["method1"]["class_name"] == "TestClass"
            assert methods_by_name["method2"]["is_abstract"] is True

            db.close()

    @pytest.mark.asyncio
    async def test_list_all_entities(self):
        """Test listing all entities."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file, class, function, and method
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Class docstring", [])
            db.add_function(file_id, "test_func", 5, [], "Function docstring")
            db.add_method(class_id, "test_method", 15, ["self"], "Method docstring")

            cmd = ListCodeEntitiesCommand(db, project_id, entity_type=None)
            result = await cmd.execute()

            assert result["success"] is True
            assert result["entity_type"] == "all"
            assert result["total"]["classes"] == 1
            assert result["total"]["functions"] == 1
            assert result["total"]["methods"] == 1
            assert len(result["entities"]["classes"]) == 1
            assert len(result["entities"]["functions"]) == 1
            assert len(result["entities"]["methods"]) == 1

            db.close()

    @pytest.mark.asyncio
    async def test_list_entities_with_file_filter(self):
        """Test listing entities filtered by file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add two files with classes
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)

            db.add_class(file1_id, "Class1", 10, "Class 1", [])
            db.add_class(file2_id, "Class2", 10, "Class 2", [])

            # List classes in file1
            cmd = ListCodeEntitiesCommand(
                db, project_id, entity_type="class", file_path="file1.py"
            )
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 1
            assert len(result["entities"]) == 1
            assert result["entities"][0]["name"] == "Class1"

            db.close()

    @pytest.mark.asyncio
    async def test_list_entities_with_limit(self):
        """Test listing entities with limit."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file with multiple classes
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            for i in range(10):
                db.add_class(file_id, f"Class{i}", 10 + i, f"Class {i}", [])

            # Get first 5
            cmd = ListCodeEntitiesCommand(db, project_id, entity_type="class", limit=5)
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 10
            assert len(result["entities"]) == 5
            assert result["limit"] == 5

            db.close()

    @pytest.mark.asyncio
    async def test_list_entities_invalid_type(self):
        """Test listing entities with invalid type."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            cmd = ListCodeEntitiesCommand(db, project_id, entity_type="invalid")
            result = await cmd.execute()

            assert result["success"] is False
            assert "unknown entity type" in result["message"].lower()

            db.close()
