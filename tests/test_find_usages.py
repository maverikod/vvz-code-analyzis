"""
Tests for find_usages command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.find_usages import FindUsagesCommand


class TestFindUsages:
    """Tests for FindUsagesCommand."""

    @pytest.mark.asyncio
    async def test_find_usages_empty(self):
        """Test finding usages in empty project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            cmd = FindUsagesCommand(db, project_id, "test_method")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 0
            assert len(result["usages"]) == 0
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_method(self):
        """Test finding usages of a method."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file and usages
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)
            
            db.add_usage(file1_id, 10, "method_call", "method", "test_method", "TestClass", "context1")
            db.add_usage(file2_id, 20, "method_call", "method", "test_method", "TestClass", "context2")
            db.add_usage(file1_id, 15, "method_call", "method", "other_method", "TestClass", "context3")
            
            cmd = FindUsagesCommand(db, project_id, "test_method", target_type="method")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 2
            assert len(result["usages"]) == 2
            
            # Check that both files are in results
            file_paths = {usage["file_path"] for usage in result["usages"]}
            assert "file1.py" in file_paths
            assert "file2.py" in file_paths
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_with_target_class(self):
        """Test finding usages with target class filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file and usages
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            db.add_usage(file_id, 10, "method_call", "method", "test_method", "Class1", "context1")
            db.add_usage(file_id, 20, "method_call", "method", "test_method", "Class2", "context2")
            
            # Find usages for test_method in Class1 only
            cmd = FindUsagesCommand(db, project_id, "test_method", target_type="method", target_class="Class1")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 1
            assert len(result["usages"]) == 1
            assert result["usages"][0]["usages"][0]["target_class"] == "Class1"
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_property(self):
        """Test finding usages of a property."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file and usages
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            db.add_usage(file_id, 10, "attribute_access", "property", "test_prop", "TestClass", "context1")
            db.add_usage(file_id, 20, "attribute_access", "property", "test_prop", "TestClass", "context2")
            
            cmd = FindUsagesCommand(db, project_id, "test_prop", target_type="property")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 2
            assert len(result["usages"]) == 1
            assert len(result["usages"][0]["usages"]) == 2
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_with_file_filter(self):
        """Test finding usages filtered by file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add two files with usages
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)
            
            db.add_usage(file1_id, 10, "method_call", "method", "test_method", "TestClass", "context1")
            db.add_usage(file2_id, 20, "method_call", "method", "test_method", "TestClass", "context2")
            
            # Find usages in file1 only
            cmd = FindUsagesCommand(db, project_id, "test_method", file_path="file1.py")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 1
            assert len(result["usages"]) == 1
            assert result["usages"][0]["file_path"] == "file1.py"
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_with_limit(self):
        """Test finding usages with limit."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file with multiple usages
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            for i in range(10):
                db.add_usage(file_id, 10 + i, "method_call", "method", "test_method", "TestClass", f"context{i}")
            
            # Get first 5
            cmd = FindUsagesCommand(db, project_id, "test_method", limit=5)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 10
            assert result["limit"] == 5
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_grouped_by_file(self):
        """Test that usages are grouped by file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file with multiple usages
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            db.add_usage(file_id, 10, "method_call", "method", "test_method", "TestClass", "context1")
            db.add_usage(file_id, 20, "method_call", "method", "test_method", "TestClass", "context2")
            db.add_usage(file_id, 30, "method_call", "method", "test_method", "TestClass", "context3")
            
            cmd = FindUsagesCommand(db, project_id, "test_method")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert len(result["usages"]) == 1
            assert result["usages"][0]["file_path"] == "test.py"
            assert len(result["usages"][0]["usages"]) == 3
            
            db.close()

    @pytest.mark.asyncio
    async def test_find_usages_all_types(self):
        """Test finding usages for all types."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file and usages of different types
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            db.add_usage(file_id, 10, "method_call", "method", "test_entity", "TestClass", "context1")
            db.add_usage(file_id, 20, "attribute_access", "property", "test_entity", "TestClass", "context2")
            
            # Find usages for test_entity (all types)
            cmd = FindUsagesCommand(db, project_id, "test_entity")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 2
            assert len(result["usages"]) == 1
            
            db.close()

