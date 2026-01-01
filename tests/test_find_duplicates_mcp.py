"""
Tests for find_duplicates MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.commands.find_duplicates_mcp import FindDuplicatesMCPCommand
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


class TestFindDuplicatesMCPCommand:
    """Tests for FindDuplicatesMCPCommand."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temporary project with test files."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        data_dir = project_dir / "data"
        data_dir.mkdir()

        # Create test Python file with duplicates
        test_file = project_dir / "test.py"
        test_file.write_text(
            """
def duplicate_func1(x, y):
    result = []
    for item in x:
        if item > 0:
            result.append(item * 2)
    return result

def duplicate_func2(a, b):
    output = []
    for element in a:
        if element > 0:
            output.append(element * 2)
    return output

def unique_func(z):
    return z + 1
"""
        )

        # Create database
        db_path = data_dir / "code_analysis.db"
        driver_config = create_driver_config_for_worker(db_path)
        db = CodeDatabase(driver_config=driver_config)

        # Add project
        project_id = db.get_or_create_project(str(project_dir), name="test_project")
        db.close()

        return {
            "root_dir": str(project_dir),
            "project_id": project_id,
            "test_file": test_file,
        }

    @pytest.mark.asyncio
    async def test_find_duplicates_in_file(self, temp_project):
        """Test finding duplicates in specific file."""
        cmd = FindDuplicatesMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
            use_semantic=False,
        )

        assert hasattr(result, "data")
        assert "duplicate_groups" in result.data
        assert result.data["total_groups"] > 0

        # Should find duplicate between duplicate_func1 and duplicate_func2
        found_duplicate = False
        for group in result.data["duplicate_groups"]:
            func_names = {occ["function_name"] for occ in group["occurrences"]}
            if "duplicate_func1" in func_names and "duplicate_func2" in func_names:
                found_duplicate = True
                break

        assert (
            found_duplicate
        ), "Should find duplicate between duplicate_func1 and duplicate_func2"

    @pytest.mark.asyncio
    async def test_min_lines_filter(self, temp_project):
        """Test filtering by min_lines."""
        cmd = FindDuplicatesMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
            min_lines=20,  # Very high threshold
            use_semantic=False,
        )

        assert hasattr(result, "data")
        # Should find fewer or no duplicates with high min_lines
        assert isinstance(result.data["total_groups"], int)

    @pytest.mark.asyncio
    async def test_min_similarity_filter(self, temp_project):
        """Test filtering by min_similarity."""
        cmd = FindDuplicatesMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
            min_similarity=0.95,  # Very high threshold
            use_semantic=False,
        )

        assert hasattr(result, "data")
        # All results should have similarity >= 0.95
        for group in result.data["duplicate_groups"]:
            assert group["similarity"] >= 0.95

    @pytest.mark.asyncio
    async def test_schema(self):
        """Test command schema."""
        schema = FindDuplicatesMCPCommand.get_schema()

        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "root_dir" in schema["properties"]
        assert "file_path" in schema["properties"]
        assert "min_lines" in schema["properties"]
        assert "min_similarity" in schema["properties"]
        assert "use_semantic" in schema["properties"]
        assert "required" in schema
        assert "root_dir" in schema["required"]

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        """Test error handling for non-existent project."""
        cmd = FindDuplicatesMCPCommand()
        result = await cmd.execute(
            root_dir="/nonexistent/path",
            project_id="nonexistent-id",
        )

        assert hasattr(result, "code")
        assert "PROJECT_NOT_FOUND" in result.code or "VALIDATION_ERROR" in result.code

    @pytest.mark.asyncio
    async def test_results_structure(self, temp_project):
        """Test that results have correct structure."""
        cmd = FindDuplicatesMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
            use_semantic=False,
        )

        assert hasattr(result, "data")
        assert "duplicate_groups" in result.data
        assert "total_groups" in result.data
        assert "total_occurrences" in result.data

        # Verify group structure
        for group in result.data["duplicate_groups"]:
            assert "hash" in group
            assert "similarity" in group
            assert "occurrences" in group
            assert len(group["occurrences"]) >= 2

            # Verify occurrence structure
            for occ in group["occurrences"]:
                assert "function_name" in occ
                assert "start_line" in occ
                assert "end_line" in occ
                assert "type" in occ
                assert "file_path" in occ
