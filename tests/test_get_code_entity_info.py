"""
Tests for get_code_entity_info command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.get_code_entity_info import GetCodeEntityInfoCommand


class TestGetCodeEntityInfo:
    """Tests for GetCodeEntityInfoCommand."""

    @pytest.mark.asyncio
    async def test_get_class_info_not_found(self):
        """Test getting info for non-existent class."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            cmd = GetCodeEntityInfoCommand(db, project_id, "class", "NonExistentClass")
            result = await cmd.execute()
            
            assert result["success"] is False
            assert "not found" in result["message"].lower()
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_class_info(self):
        """Test getting info for a class."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            # Add class
            class_id = db.add_class(file_id, "TestClass", 10, "Test class docstring", ["BaseClass"])
            
            # Add methods
            method1_id = db.add_method(class_id, "method1", 15, ["self", "arg1"], "Method 1 docstring")
            method2_id = db.add_method(class_id, "method2", 25, ["self"], "Method 2 docstring", is_abstract=True)
            
            cmd = GetCodeEntityInfoCommand(db, project_id, "class", "TestClass")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["entity_type"] == "class"
            assert result["entity_name"] == "TestClass"
            assert result["id"] == class_id
            assert result["line"] == 10
            assert result["docstring"] == "Test class docstring"
            assert result["bases"] == ["BaseClass"]
            assert len(result["methods"]) == 2
            assert result["method_count"] == 2
            assert result["file"]["id"] == file_id
            
            # Check methods
            methods_by_name = {m["name"]: m for m in result["methods"]}
            assert "method1" in methods_by_name
            assert "method2" in methods_by_name
            assert methods_by_name["method1"]["args"] == ["self", "arg1"]
            assert methods_by_name["method2"]["is_abstract"] is True
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_function_info(self):
        """Test getting info for a function."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            # Add function
            func_id = db.add_function(file_id, "test_function", 20, ["arg1", "arg2"], "Function docstring")
            
            cmd = GetCodeEntityInfoCommand(db, project_id, "function", "test_function")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["entity_type"] == "function"
            assert result["entity_name"] == "test_function"
            assert result["id"] == func_id
            assert result["line"] == 20
            assert result["args"] == ["arg1", "arg2"]
            assert result["docstring"] == "Function docstring"
            assert result["file"]["id"] == file_id
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_method_info(self):
        """Test getting info for a method."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file and class
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Class docstring", [])
            
            # Add method
            method_id = db.add_method(class_id, "test_method", 15, ["self", "arg1"], "Method docstring")
            
            cmd = GetCodeEntityInfoCommand(db, project_id, "method", "test_method")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["entity_type"] == "method"
            assert result["entity_name"] == "test_method"
            assert result["id"] == method_id
            assert result["line"] == 15
            assert result["args"] == ["self", "arg1"]
            assert result["docstring"] == "Method docstring"
            assert result["class"]["id"] == class_id
            assert result["class"]["name"] == "TestClass"
            assert result["file"]["id"] == file_id
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_entity_with_file_path(self):
        """Test getting entity info with file path filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add two files with same class name
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)
            
            class1_id = db.add_class(file1_id, "SameName", 10, "Class 1", [])
            class2_id = db.add_class(file2_id, "SameName", 10, "Class 2", [])
            
            # Get class from file1
            cmd = GetCodeEntityInfoCommand(db, project_id, "class", "SameName", file_path="file1.py")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["id"] == class1_id
            assert result["docstring"] == "Class 1"
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_entity_with_line(self):
        """Test getting entity info with line number filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            # Add two functions with same name at different lines
            func1_id = db.add_function(file_id, "same_name", 10, [], "Function 1")
            func2_id = db.add_function(file_id, "same_name", 20, [], "Function 2")
            
            # Get function at line 20
            cmd = GetCodeEntityInfoCommand(db, project_id, "function", "same_name", line=20)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["id"] == func2_id
            assert result["docstring"] == "Function 2"
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_entity_invalid_type(self):
        """Test getting entity info with invalid entity type."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            cmd = GetCodeEntityInfoCommand(db, project_id, "invalid_type", "Test")
            result = await cmd.execute()
            
            assert result["success"] is False
            assert "unknown entity type" in result["message"].lower()
            
            db.close()

    @pytest.mark.asyncio
    async def test_get_class_with_chunks(self):
        """Test getting class info includes chunk count."""
        import uuid
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file and class
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            class_id = db.add_class(file_id, "TestClass", 10, "Class docstring", [])
            
            # Add chunks
            await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid=str(uuid.uuid4()),
                chunk_text="Chunk 1",
                chunk_type="DocBlock",
                class_id=class_id,
            )
            await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid=str(uuid.uuid4()),
                chunk_text="Chunk 2",
                chunk_type="DocBlock",
                class_id=class_id,
            )
            
            cmd = GetCodeEntityInfoCommand(db, project_id, "class", "TestClass")
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["chunk_count"] == 2
            
            db.close()

