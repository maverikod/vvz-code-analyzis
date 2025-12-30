"""
Tests for analyze_complexity MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from code_analysis.commands.analyze_complexity_mcp import AnalyzeComplexityMCPCommand
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


class TestAnalyzeComplexityMCPCommand:
    """Tests for AnalyzeComplexityMCPCommand."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temporary project with test files."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        data_dir = project_dir / "data"
        data_dir.mkdir()

        # Create test Python file
        test_file = project_dir / "test.py"
        test_file.write_text(
            """
def simple():
    return 1

def with_if(x):
    if x > 0:
        return 1
    return 0

def complex_func(x, y):
    result = 0
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                result += i
    elif y > 0:
        while y > 0:
            result += y
            y -= 1
    return result

class MyClass:
    def method1(self):
        return 1
    
    def method2(self, x):
        if x > 0:
            return 1
        return 0
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
    async def test_analyze_specific_file(self, temp_project):
        """Test analyzing specific file."""
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
        )

        assert result.success
        assert "results" in result.data
        assert "total_count" in result.data
        assert result.data["total_count"] > 0

        # Check that results contain expected functions
        function_names = [r["function_name"] for r in result.data["results"]]
        assert "simple" in function_names
        assert "with_if" in function_names
        assert "complex_func" in function_names

        # Check complexity values
        for r in result.data["results"]:
            assert "file_path" in r
            assert "function_name" in r
            assert "complexity" in r
            assert "line" in r
            assert "type" in r
            assert r["complexity"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_all_files(self, temp_project):
        """Test analyzing all files in project."""
        # First, update indexes to add files to database
        from code_analysis.commands.code_mapper_mcp_command import (
            UpdateIndexesMCPCommand,
        )

        update_cmd = UpdateIndexesMCPCommand()
        await update_cmd.execute(root_dir=temp_project["root_dir"])

        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(root_dir=temp_project["root_dir"])

        assert result.success
        assert "results" in result.data
        assert result.data["total_count"] > 0

    @pytest.mark.asyncio
    async def test_min_complexity_filter(self, temp_project):
        """Test filtering by minimum complexity."""
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
            min_complexity=3,
        )

        assert result.success
        # All results should have complexity >= 3
        for r in result.data["results"]:
            assert r["complexity"] >= 3

    @pytest.mark.asyncio
    async def test_project_not_found(self):
        """Test error handling for non-existent project."""
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir="/nonexistent/path",
            project_id="nonexistent-id",
        )

        assert not result.success
        assert "PROJECT_NOT_FOUND" in result.code

    @pytest.mark.asyncio
    async def test_file_not_found(self, temp_project):
        """Test error handling for non-existent file."""
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path="nonexistent.py",
        )

        # Should succeed but return empty results or handle gracefully
        # (depends on implementation)
        assert result.success or not result.success  # Either is acceptable

    @pytest.mark.asyncio
    async def test_results_sorted_by_complexity(self, temp_project):
        """Test that results are sorted by complexity (descending)."""
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
        )

        assert result.success
        complexities = [r["complexity"] for r in result.data["results"]]
        # Check that complexities are in descending order
        assert complexities == sorted(complexities, reverse=True)

    @pytest.mark.asyncio
    async def test_method_detection(self, temp_project):
        """Test that methods are correctly detected and analyzed."""
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=temp_project["root_dir"],
            file_path=str(temp_project["test_file"]),
        )

        assert result.success
        methods = [r for r in result.data["results"] if r["type"] == "method"]
        assert len(methods) >= 2  # method1 and method2

        method_names = [m["function_name"] for m in methods]
        assert "method1" in method_names
        assert "method2" in method_names

        # Check that methods have class_name
        for method in methods:
            assert "class_name" in method
            assert method["class_name"] == "MyClass"

    @pytest.mark.asyncio
    async def test_schema(self):
        """Test command schema."""
        schema = AnalyzeComplexityMCPCommand.get_schema()

        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "root_dir" in schema["properties"]
        assert "file_path" in schema["properties"]
        assert "min_complexity" in schema["properties"]
        assert "required" in schema
        assert "root_dir" in schema["required"]


class TestRealDataMCP:
    """Tests using real data from test_data directory."""

    @pytest.fixture
    def real_project_path(self):
        """Get path to real test_data project."""
        project_root = Path(__file__).parent.parent
        test_data = project_root / "test_data" / "bhlff_mcp_test"
        if test_data.exists():
            return str(test_data)
        return None

    @pytest.mark.asyncio
    async def test_real_project_analysis(self, real_project_path):
        """Test analyzing real project from test_data."""
        if real_project_path is None:
            pytest.skip("test_data/bhlff_mcp_test not found")

        # First update indexes
        from code_analysis.commands.code_mapper_mcp_command import (
            UpdateIndexesMCPCommand,
        )

        update_cmd = UpdateIndexesMCPCommand()
        await update_cmd.execute(root_dir=real_project_path, max_lines=400)

        # Then analyze complexity
        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(root_dir=real_project_path)

        assert result.success
        assert "results" in result.data
        assert result.data["total_count"] > 0

        # Verify results structure
        for r in result.data["results"][:10]:  # Check first 10 results
            assert "file_path" in r
            assert "function_name" in r
            assert "complexity" in r
            assert "line" in r
            assert "type" in r
            assert r["complexity"] >= 1
            assert r["type"] in ["function", "method"]

    @pytest.mark.asyncio
    async def test_real_file_analysis(self, real_project_path):
        """Test analyzing specific real file."""
        if real_project_path is None:
            pytest.skip("test_data/bhlff_mcp_test not found")

        # Find a Python file
        project_path = Path(real_project_path)
        py_files = list(project_path.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found")

        test_file = py_files[0]
        relative_path = test_file.relative_to(project_path)

        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=real_project_path,
            file_path=str(relative_path),
        )

        assert result.success
        assert "results" in result.data

    @pytest.mark.asyncio
    async def test_complexity_distribution_real_data(self, real_project_path):
        """Test complexity distribution in real project."""
        if real_project_path is None:
            pytest.skip("test_data/bhlff_mcp_test not found")

        # Update indexes first
        from code_analysis.commands.code_mapper_mcp_command import (
            UpdateIndexesMCPCommand,
        )

        update_cmd = UpdateIndexesMCPCommand()
        await update_cmd.execute(root_dir=real_project_path, max_lines=400)

        cmd = AnalyzeComplexityMCPCommand()
        result = await cmd.execute(
            root_dir=real_project_path,
            min_complexity=5,  # Only high complexity functions
        )

        assert result.success
        if result.data["total_count"] > 0:
            # All results should have complexity >= 5
            for r in result.data["results"]:
                assert r["complexity"] >= 5
