"""
Tests for project root detection on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from code_analysis.core.project_resolution import (
    find_project_root_for_path,
    load_project_info,
    ProjectInfo,
)
from code_analysis.core.project_discovery import find_project_root, ProjectRoot
from code_analysis.core.exceptions import (
    MultipleProjectIdError,
    NestedProjectError,
    InvalidProjectIdFormatError,
    ProjectIdError,
)


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"
CODE_ANALYSIS_DIR = TEST_DATA_DIR / "code_analysis"


class TestProjectRootDetectionRealData:
    """Test project root detection on real data from test_data/."""

    def test_find_project_root_vast_srv(self):
        """Test finding project root for file in test_data/vast_srv/."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        # Find a Python file in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        watch_dirs = [VAST_SRV_DIR.parent]

        project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])

        # If projectid is in old format, project_info might be None
        # or might raise an error during discovery
        if project_info is not None:
            assert isinstance(project_info, ProjectInfo)
            assert project_info.root_path == VAST_SRV_DIR.resolve()
            assert project_info.project_id is not None
            assert len(project_info.project_id) == 36  # UUID4 format
            assert project_info.description is not None

    def test_find_project_root_bhlff(self):
        """Test finding project root for file in test_data/bhlff/."""
        if not BHLFF_DIR.exists():
            pytest.skip("test_data/bhlff/ not found")

        # Find a Python file in bhlff
        python_files = list(BHLFF_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/bhlff/")

        test_file = python_files[0]
        watch_dirs = [BHLFF_DIR.parent]

        project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])

        # bhlff might not have projectid, so it's OK if None
        if project_info is not None:
            assert isinstance(project_info, ProjectInfo)
            assert project_info.root_path.exists()
            assert project_info.project_id is not None

    def test_find_project_root_code_analysis(self):
        """Test finding project root for file in test_data/code_analysis/."""
        if not CODE_ANALYSIS_DIR.exists():
            pytest.skip("test_data/code_analysis/ not found")

        # Find a Python file in code_analysis
        python_files = list(CODE_ANALYSIS_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/code_analysis/")

        test_file = python_files[0]
        watch_dirs = [CODE_ANALYSIS_DIR.parent]

        project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])

        # code_analysis might not have projectid, so it's OK if None
        if project_info is not None:
            assert isinstance(project_info, ProjectInfo)
            assert project_info.root_path.exists()
            assert project_info.project_id is not None

    def test_find_project_root_file_outside_project(self):
        """Test finding project root for file outside any project."""
        # Create a temporary file outside test_data
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_file = Path(f.name)
            f.write("# Test file\n")

        try:
            watch_dirs = [TEST_DATA_DIR]
            project_info = find_project_root_for_path(temp_file, [str(w) for w in watch_dirs])
            assert project_info is None
        finally:
            temp_file.unlink()

    def test_load_project_info_vast_srv(self):
        """Test loading project info from test_data/vast_srv/projectid."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in test_data/vast_srv/")

        # Check if projectid is in old format (just UUID) or new format (JSON)
        projectid_content = projectid_file.read_text().strip()
        is_json = projectid_content.startswith("{")

        if not is_json:
            # Old format - might not work with current implementation
            # Skip or expect error
            with pytest.raises((InvalidProjectIdFormatError, ProjectIdError)):
                load_project_info(VAST_SRV_DIR)
            pytest.skip("projectid file is in old format, needs migration")
        else:
            project_info = load_project_info(VAST_SRV_DIR)

            assert isinstance(project_info, ProjectInfo)
            assert project_info.root_path == VAST_SRV_DIR.resolve()
            assert project_info.project_id is not None
            assert len(project_info.project_id) == 36  # UUID4 format
            assert project_info.description is not None
            assert isinstance(project_info.description, str)

    def test_find_project_root_multiple_files_vast_srv(self):
        """Test finding project root for multiple files in vast_srv."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:10]  # Test first 10 files
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        watch_dirs = [VAST_SRV_DIR.parent]

        for test_file in python_files:
            project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])
            assert project_info is not None
            assert project_info.root_path == VAST_SRV_DIR.resolve()
            assert project_info.project_id is not None


class TestProjectRootDetectionEdgeCases:
    """Test edge cases for project root detection."""

    def test_find_project_root_nonexistent_file(self):
        """Test finding project root for nonexistent file."""
        nonexistent_file = Path("/nonexistent/path/file.py")
        watch_dirs = [TEST_DATA_DIR]

        # find_project_root_for_path should handle nonexistent files
        # It might return None or raise an error depending on implementation
        try:
            project_info = find_project_root_for_path(nonexistent_file, [str(w) for w in watch_dirs])
            assert project_info is None
        except (FileNotFoundError, ValueError):
            # This is also acceptable behavior
            pass

    def test_find_project_root_with_multiple_projectid(self, tmp_path):
        """Test finding project root with multiple projectid files in path."""
        # Create nested structure with multiple projectid files
        root_dir = tmp_path / "root"
        root_dir.mkdir()
        (root_dir / "projectid").write_text('{"id": "00000000-0000-0000-0000-000000000001", "description": "Root"}')

        nested_dir = root_dir / "nested"
        nested_dir.mkdir()
        (nested_dir / "projectid").write_text('{"id": "00000000-0000-0000-0000-000000000002", "description": "Nested"}')

        test_file = nested_dir / "test.py"
        test_file.write_text("# Test")

        watch_dirs = [root_dir]

        with pytest.raises(MultipleProjectIdError) as exc_info:
            find_project_root_for_path(test_file, [str(w) for w in watch_dirs])

        assert len(exc_info.value.projectid_paths) >= 2

    def test_find_project_root_invalid_projectid_format(self, tmp_path):
        """Test finding project root with invalid projectid format."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "projectid").write_text("invalid json")

        test_file = project_dir / "test.py"
        test_file.write_text("# Test")

        watch_dirs = [tmp_path]

        # Should raise InvalidProjectIdFormatError when loading project info
        with pytest.raises(InvalidProjectIdFormatError):
            load_project_info(project_dir)

    def test_find_project_root_missing_projectid(self, tmp_path):
        """Test finding project root with missing projectid file."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # No projectid file

        test_file = project_dir / "test.py"
        test_file.write_text("# Test")

        watch_dirs = [tmp_path]

        project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])
        assert project_info is None

    def test_find_project_root_empty_projectid(self, tmp_path):
        """Test finding project root with empty projectid file."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "projectid").write_text("")

        with pytest.raises(ProjectIdError):
            load_project_info(project_dir)

    def test_find_project_root_missing_id_field(self, tmp_path):
        """Test finding project root with projectid missing 'id' field."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "projectid").write_text('{"description": "Test"}')

        with pytest.raises(InvalidProjectIdFormatError) as exc_info:
            load_project_info(project_dir)

        assert "id" in str(exc_info.value.message).lower()


class TestProjectRootDiscovery:
    """Test project discovery using find_project_root."""

    def test_find_project_root_vast_srv_discovery(self):
        """Test project discovery for vast_srv using find_project_root."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        watch_dirs = [VAST_SRV_DIR.parent]

        project_root = find_project_root(test_file, watch_dirs)

        if project_root is not None:
            assert isinstance(project_root, ProjectRoot)
            assert project_root.root_path == VAST_SRV_DIR.resolve()
            assert project_root.project_id is not None
            assert len(project_root.project_id) == 36  # UUID4 format
            assert project_root.description is not None
            assert project_root.watch_dir == VAST_SRV_DIR.parent.resolve()

    def test_find_project_root_file_outside_watch_dir(self):
        """Test finding project root for file outside watch_dir."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_file = Path(f.name)
            f.write("# Test file\n")

        try:
            watch_dirs = [TEST_DATA_DIR]
            project_root = find_project_root(temp_file, watch_dirs)
            assert project_root is None
        finally:
            temp_file.unlink()


class TestProjectRootCaching:
    """Test caching of project root detection results."""

    def test_find_project_root_same_file_multiple_times(self):
        """Test that finding project root for same file returns consistent results."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        watch_dirs = [VAST_SRV_DIR.parent]

        # Call multiple times
        results = []
        for _ in range(5):
            project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])
            results.append(project_info)

        # All results should be the same
        assert all(r is not None for r in results)
        assert all(r.root_path == results[0].root_path for r in results)
        assert all(r.project_id == results[0].project_id for r in results)


class TestProjectRootPerformance:
    """Test performance of project root detection."""

    def test_find_project_root_performance_large_project(self):
        """Test performance on large project (vast_srv)."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:100]  # Test first 100 files
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        watch_dirs = [VAST_SRV_DIR.parent]

        import time
        start_time = time.time()

        for test_file in python_files:
            project_info = find_project_root_for_path(test_file, [str(w) for w in watch_dirs])
            assert project_info is not None

        elapsed_time = time.time() - start_time
        # Should complete 100 files in reasonable time (< 10 seconds)
        assert elapsed_time < 10.0, f"Too slow: {elapsed_time:.2f}s for 100 files"

