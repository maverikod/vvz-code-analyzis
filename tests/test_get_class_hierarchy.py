"""
Tests for get_class_hierarchy command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.get_class_hierarchy import GetClassHierarchyCommand


class TestGetClassHierarchy:
    """Tests for GetClassHierarchyCommand."""

    @pytest.mark.asyncio
    async def test_get_hierarchy_empty(self):
        """Test getting hierarchy in empty project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            cmd = GetClassHierarchyCommand(db, project_id)
            result = await cmd.execute()

            assert result["success"] is True
            assert len(result["hierarchies"]) == 0
            assert result["total_classes"] == 0

            db.close()

    @pytest.mark.asyncio
    async def test_get_hierarchy_single_class(self):
        """Test getting hierarchy for single class without inheritance."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and class
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_class(file_id, "TestClass", 10, "Class docstring", [])

            cmd = GetClassHierarchyCommand(db, project_id, class_name="TestClass")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["class_name"] == "TestClass"
            assert result["hierarchy"]["name"] == "TestClass"
            assert result["hierarchy"]["bases"] == []
            assert result["hierarchy"]["children"] == []

            db.close()

    @pytest.mark.asyncio
    async def test_get_hierarchy_with_inheritance(self):
        """Test getting hierarchy with inheritance."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and classes
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_class(file_id, "BaseClass", 10, "Base class", [])
            db.add_class(file_id, "DerivedClass", 20, "Derived class", ["BaseClass"])

            # Get hierarchy for derived class
            cmd = GetClassHierarchyCommand(db, project_id, class_name="DerivedClass")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["class_name"] == "DerivedClass"
            assert len(result["hierarchy"]["bases"]) == 1
            assert result["hierarchy"]["bases"][0]["name"] == "BaseClass"

            # Get hierarchy for base class
            cmd2 = GetClassHierarchyCommand(db, project_id, class_name="BaseClass")
            result2 = await cmd2.execute()

            assert result2["success"] is True
            assert len(result2["hierarchy"]["children"]) == 1
            assert result2["hierarchy"]["children"][0]["name"] == "DerivedClass"

            db.close()

    @pytest.mark.asyncio
    async def test_get_hierarchy_multiple_inheritance(self):
        """Test getting hierarchy with multiple inheritance."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and classes
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_class(file_id, "Base1", 10, "Base 1", [])
            db.add_class(file_id, "Base2", 15, "Base 2", [])
            db.add_class(file_id, "Derived", 20, "Derived", ["Base1", "Base2"])

            cmd = GetClassHierarchyCommand(db, project_id, class_name="Derived")
            result = await cmd.execute()

            assert result["success"] is True
            assert len(result["hierarchy"]["bases"]) == 2
            base_names = {b["name"] for b in result["hierarchy"]["bases"]}
            assert "Base1" in base_names
            assert "Base2" in base_names

            db.close()

    @pytest.mark.asyncio
    async def test_get_all_hierarchies(self):
        """Test getting all hierarchies."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and classes
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            db.add_class(file_id, "BaseClass", 10, "Base class", [])
            db.add_class(file_id, "DerivedClass", 20, "Derived class", ["BaseClass"])
            db.add_class(file_id, "StandaloneClass", 30, "Standalone", [])

            cmd = GetClassHierarchyCommand(db, project_id)
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total_classes"] == 3
            assert (
                len(result["hierarchies"]) >= 2
            )  # At least BaseClass and StandaloneClass

            # Check that hierarchies are present
            hierarchy_names = {h["name"] for h in result["hierarchies"]}
            assert (
                "BaseClass" in hierarchy_names or "StandaloneClass" in hierarchy_names
            )

            db.close()

    @pytest.mark.asyncio
    async def test_get_hierarchy_class_not_found(self):
        """Test getting hierarchy for non-existent class."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            cmd = GetClassHierarchyCommand(db, project_id, class_name="NonExistent")
            result = await cmd.execute()

            assert result["success"] is False
            assert "not found" in result["message"].lower()

            db.close()

    @pytest.mark.asyncio
    async def test_get_hierarchy_with_file_filter(self):
        """Test getting hierarchy filtered by file."""
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

            # Get hierarchy for file1 only
            cmd = GetClassHierarchyCommand(db, project_id, file_path="file1.py")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total_classes"] == 1
            assert len(result["hierarchies"]) == 1
            assert result["hierarchies"][0]["name"] == "Class1"

            db.close()
