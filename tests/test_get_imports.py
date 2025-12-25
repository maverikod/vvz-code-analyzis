"""
Tests for get_imports command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from code_analysis.core.database import CodeDatabase
from code_analysis.commands.get_imports import GetImportsCommand


class TestGetImports:
    """Tests for GetImportsCommand."""

    @pytest.mark.asyncio
    async def test_get_imports_empty(self):
        """Test getting imports in empty project."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            cmd = GetImportsCommand(db, project_id)
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 0
            assert len(result["imports"]) == 0

            db.close()

    @pytest.mark.asyncio
    async def test_get_imports(self):
        """Test getting imports."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and imports
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            db.add_import(file_id, "os", None, "import", 1)
            db.add_import(file_id, "sys", None, "import", 2)
            db.add_import(file_id, "pathlib", "pathlib", "import_from", 3)
            db.add_import(file_id, "Path", "pathlib", "import_from", 4)

            cmd = GetImportsCommand(db, project_id)
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 4
            assert len(result["imports"]) == 4

            imports_by_name = {imp["name"]: imp for imp in result["imports"]}
            assert "os" in imports_by_name
            assert "sys" in imports_by_name
            assert "pathlib" in imports_by_name
            assert "Path" in imports_by_name

            assert imports_by_name["os"]["import_type"] == "import"
            assert imports_by_name["Path"]["import_type"] == "import_from"
            assert imports_by_name["Path"]["module"] == "pathlib"

            db.close()

    @pytest.mark.asyncio
    async def test_get_imports_by_type(self):
        """Test getting imports filtered by type."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and imports
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            db.add_import(file_id, "os", None, "import", 1)
            db.add_import(file_id, "sys", None, "import", 2)
            db.add_import(file_id, "Path", "pathlib", "import_from", 3)

            # Get only import statements
            cmd = GetImportsCommand(db, project_id, import_type="import")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 2
            assert len(result["imports"]) == 2
            assert all(imp["import_type"] == "import" for imp in result["imports"])

            db.close()

    @pytest.mark.asyncio
    async def test_get_imports_by_module(self):
        """Test getting imports filtered by module name."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file and imports
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)

            db.add_import(file_id, "os", None, "import", 1)
            db.add_import(file_id, "Path", "pathlib", "import_from", 2)
            db.add_import(file_id, "PurePath", "pathlib", "import_from", 3)
            db.add_import(file_id, "json", None, "import", 4)

            # Get imports from pathlib
            cmd = GetImportsCommand(db, project_id, module_name="pathlib")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 2
            assert len(result["imports"]) == 2
            assert all(imp["module"] == "pathlib" for imp in result["imports"])

            db.close()

    @pytest.mark.asyncio
    async def test_get_imports_by_file(self):
        """Test getting imports filtered by file."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add two files with imports
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)

            db.add_import(file1_id, "os", None, "import", 1)
            db.add_import(file2_id, "sys", None, "import", 1)

            # Get imports from file1
            cmd = GetImportsCommand(db, project_id, file_path="file1.py")
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 1
            assert len(result["imports"]) == 1
            assert result["imports"][0]["name"] == "os"

            db.close()

    @pytest.mark.asyncio
    async def test_get_imports_with_limit(self):
        """Test getting imports with limit."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add file with multiple imports
            file_id = db.add_file("test.py", 100, 1234567890.0, True, project_id)
            for i in range(10):
                db.add_import(file_id, f"module{i}", None, "import", i + 1)

            # Get first 5
            cmd = GetImportsCommand(db, project_id, limit=5)
            result = await cmd.execute()

            assert result["success"] is True
            assert result["total"] == 10
            assert len(result["imports"]) == 5
            assert result["limit"] == 5

            db.close()

    @pytest.mark.asyncio
    async def test_get_imports_file_summary(self):
        """Test that file summary is included in result."""
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data" / "code_analysis.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = CodeDatabase(db_path)

            project_id = db.get_or_create_project(str(tmpdir), name="test_project")

            # Add two files with imports
            file1_id = db.add_file("file1.py", 100, 1234567890.0, True, project_id)
            file2_id = db.add_file("file2.py", 100, 1234567891.0, True, project_id)

            db.add_import(file1_id, "os", None, "import", 1)
            db.add_import(file1_id, "sys", None, "import", 2)
            db.add_import(file2_id, "Path", "pathlib", "import_from", 1)

            cmd = GetImportsCommand(db, project_id)
            result = await cmd.execute()

            assert result["success"] is True
            assert "file_summary" in result
            assert len(result["file_summary"]) == 2

            summary_by_file = {s["file_path"]: s for s in result["file_summary"]}
            assert "file1.py" in summary_by_file
            assert summary_by_file["file1.py"]["import_count"] == 2
            assert summary_by_file["file1.py"]["import_types"]["import"] == 2

            db.close()
