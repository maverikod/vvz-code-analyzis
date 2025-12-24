"""
Tests for list_project_files command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.list_project_files import ListProjectFilesCommand


class TestListProjectFiles:
    """Tests for ListProjectFilesCommand."""

    @pytest.mark.asyncio
    async def test_list_files_empty_project(self):
        """Test listing files in empty project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            cmd = ListProjectFilesCommand(db, project_id)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 0
            assert len(result["files"]) == 0
            
            db.close()

    @pytest.mark.asyncio
    async def test_list_files_with_data(self):
        """Test listing files with actual data."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add some files
            file1_id = db.add_file("test1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("test2.py", 200, 1234567891.0, False, project_id)
            file3_id = db.add_file("core/module.py", 150, 1234567892.0, True, project_id)
            
            # Add some classes and functions
            class_id = db.add_class(file1_id, "TestClass", 10, "Test docstring", "[]")
            func_id = db.add_function(file1_id, "test_func", 20, "Function docstring", None)
            
            cmd = ListProjectFilesCommand(db, project_id)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 3
            assert len(result["files"]) == 3
            
            # Check file data
            files_by_path = {f["path"]: f for f in result["files"]}
            assert "test1.py" in files_by_path
            assert "test2.py" in files_by_path
            assert "core/module.py" in files_by_path
            
            # Check test1.py has class and function
            test1 = files_by_path["test1.py"]
            assert test1["class_count"] == 1
            assert test1["function_count"] == 1
            assert test1["has_docstring"] is True
            
            # Check test2.py has no classes/functions
            test2 = files_by_path["test2.py"]
            assert test2["class_count"] == 0
            assert test2["function_count"] == 0
            assert test2["has_docstring"] is False
            
            db.close()

    @pytest.mark.asyncio
    async def test_list_files_with_pattern(self):
        """Test listing files with pattern filter."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add files
            db.add_file("test1.py", 100, 1234567890.0, True, project_id)
            db.add_file("test2.py", 200, 1234567891.0, False, project_id)
            db.add_file("core/module.py", 150, 1234567892.0, True, project_id)
            db.add_file("utils/helper.py", 120, 1234567893.0, True, project_id)
            
            # Filter by pattern
            cmd = ListProjectFilesCommand(db, project_id, file_pattern="*.py")
            result = await cmd.execute()
            
            assert result["success"] is True
            # Should match all .py files
            assert result["total"] == 4
            
            # Filter by directory
            cmd2 = ListProjectFilesCommand(db, project_id, file_pattern="core/*")
            result2 = await cmd2.execute()
            
            assert result2["success"] is True
            assert result2["total"] == 1
            assert result2["files"][0]["path"] == "core/module.py"
            
            db.close()

    @pytest.mark.asyncio
    async def test_list_files_with_limit(self):
        """Test listing files with limit."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add multiple files
            for i in range(10):
                db.add_file(f"test{i}.py", 100, 1234567890.0 + i, True, project_id)
            
            # Get first 5
            cmd = ListProjectFilesCommand(db, project_id, limit=5)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 10
            assert len(result["files"]) == 5
            assert result["limit"] == 5
            
            db.close()

    @pytest.mark.asyncio
    async def test_list_files_with_offset(self):
        """Test listing files with offset."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add multiple files
            for i in range(10):
                db.add_file(f"test{i}.py", 100, 1234567890.0 + i, True, project_id)
            
            # Get with offset
            cmd = ListProjectFilesCommand(db, project_id, limit=3, offset=2)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert result["total"] == 10
            assert len(result["files"]) == 3
            assert result["offset"] == 2
            
            db.close()

    @pytest.mark.asyncio
    async def test_list_files_with_ast_info(self):
        """Test listing files includes AST information."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            # Add AST tree - skip for now as it requires async save_ast_tree
            # This test verifies that has_ast field is returned correctly
            # In real scenario, AST would be added during analysis
            
            cmd = ListProjectFilesCommand(db, project_id)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert len(result["files"]) == 1
            # Without AST tree, has_ast should be False
            assert result["files"][0]["has_ast"] is False
            
            db.close()

    @pytest.mark.asyncio
    async def test_list_files_with_chunks(self):
        """Test listing files includes chunk count."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)
            
            project_id = db.get_or_create_project(str(tmpdir), name="test_project")
            
            # Add file
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            
            # Add chunks
            await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid=str(uuid.uuid4()),
                chunk_text="Test chunk 1",
                chunk_type="DocBlock",
                source_type="docstring",
                line=10,
            )
            await db.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid=str(uuid.uuid4()),
                chunk_text="Test chunk 2",
                chunk_type="DocBlock",
                source_type="docstring",
                line=20,
            )
            
            cmd = ListProjectFilesCommand(db, project_id)
            result = await cmd.execute()
            
            assert result["success"] is True
            assert len(result["files"]) == 1
            assert result["files"][0]["chunk_count"] == 2
            
            db.close()

