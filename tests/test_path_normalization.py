"""
Tests for path normalization on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path
from code_analysis.core.path_normalization import (
    normalize_file_path,
    NormalizedPath,
)
from code_analysis.core.exceptions import (
    ProjectNotFoundError,
    MultipleProjectIdError,
)


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestPathNormalizationRealData:
    """Test path normalization on real data from test_data/."""

    def test_normalize_absolute_path_vast_srv(self):
        """Test normalizing absolute path for file in vast_srv."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        watch_dirs = [VAST_SRV_DIR.parent]

        normalized = normalize_file_path(test_file, watch_dirs=watch_dirs)

        assert isinstance(normalized, NormalizedPath)
        assert normalized.absolute_path == str(test_file.resolve())
        assert normalized.project_root == VAST_SRV_DIR.resolve()
        assert normalized.project_id is not None
        assert len(normalized.project_id) == 36  # UUID4 format
        assert normalized.relative_path is not None
        assert Path(normalized.absolute_path).exists()

    def test_normalize_relative_path_vast_srv(self):
        """Test normalizing relative path for file in vast_srv."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        # Use relative path
        relative_file = test_file.relative_to(Path.cwd())
        watch_dirs = [VAST_SRV_DIR.parent]

        normalized = normalize_file_path(relative_file, watch_dirs=watch_dirs)

        assert isinstance(normalized, NormalizedPath)
        assert normalized.absolute_path == str(test_file.resolve())
        assert normalized.project_root == VAST_SRV_DIR.resolve()
        assert normalized.project_id is not None

    def test_normalize_path_with_project_root(self):
        """Test normalizing path with explicit project_root."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]

        normalized = normalize_file_path(test_file, project_root=VAST_SRV_DIR)

        assert isinstance(normalized, NormalizedPath)
        assert normalized.absolute_path == str(test_file.resolve())
        assert normalized.project_root == VAST_SRV_DIR.resolve()
        assert normalized.project_id is not None
        assert normalized.relative_path is not None

    def test_normalize_path_multiple_files_vast_srv(self):
        """Test normalizing multiple files from vast_srv."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:20]  # Test first 20 files
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        watch_dirs = [VAST_SRV_DIR.parent]

        for test_file in python_files:
            normalized = normalize_file_path(test_file, watch_dirs=watch_dirs)
            assert isinstance(normalized, NormalizedPath)
            assert normalized.project_root == VAST_SRV_DIR.resolve()
            assert normalized.project_id is not None
            assert normalized.relative_path is not None

    def test_normalize_path_bhlff(self):
        """Test normalizing path for file in bhlff."""
        if not BHLFF_DIR.exists():
            pytest.skip("test_data/bhlff/ not found")

        python_files = list(BHLFF_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/bhlff/")

        test_file = python_files[0]
        watch_dirs = [BHLFF_DIR.parent]

        # bhlff might not have projectid, so might raise ProjectNotFoundError
        try:
            normalized = normalize_file_path(test_file, watch_dirs=watch_dirs)
            assert isinstance(normalized, NormalizedPath)
            assert normalized.absolute_path == str(test_file.resolve())
            assert normalized.project_id is not None
        except ProjectNotFoundError:
            # This is OK if bhlff doesn't have projectid
            pass


class TestPathNormalizationEdgeCases:
    """Test edge cases for path normalization."""

    def test_normalize_path_nonexistent_file(self):
        """Test normalizing path for nonexistent file."""
        nonexistent_file = Path("/nonexistent/path/file.py")
        watch_dirs = [TEST_DATA_DIR]

        with pytest.raises(FileNotFoundError):
            normalize_file_path(nonexistent_file, watch_dirs=watch_dirs)

    def test_normalize_path_outside_project(self):
        """Test normalizing path for file outside any project."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_file = Path(f.name)
            f.write("# Test file\n")

        try:
            watch_dirs = [TEST_DATA_DIR]
            with pytest.raises(ProjectNotFoundError):
                normalize_file_path(temp_file, watch_dirs=watch_dirs)
        finally:
            temp_file.unlink()

    def test_normalize_path_with_dot_dot(self):
        """Test normalizing path with .. components."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        # Create path with .. components
        parent_dir = test_file.parent.parent
        path_with_dot_dot = parent_dir / ".." / test_file.name
        watch_dirs = [VAST_SRV_DIR.parent]

        normalized = normalize_file_path(path_with_dot_dot, watch_dirs=watch_dirs)

        assert isinstance(normalized, NormalizedPath)
        assert normalized.absolute_path == str(test_file.resolve())

    def test_normalize_path_with_dot(self):
        """Test normalizing path with . components."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        # Create path with . components
        path_with_dot = test_file.parent / "." / test_file.name
        watch_dirs = [VAST_SRV_DIR.parent]

        normalized = normalize_file_path(path_with_dot, watch_dirs=watch_dirs)

        assert isinstance(normalized, NormalizedPath)
        assert normalized.absolute_path == str(test_file.resolve())

    def test_normalize_path_file_not_in_project_root(self):
        """Test normalizing path when file is not within provided project_root."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            temp_file = Path(f.name)
            f.write("# Test file\n")

        try:
            # Try to normalize file outside project_root
            with pytest.raises(ProjectNotFoundError):
                normalize_file_path(temp_file, project_root=VAST_SRV_DIR)
        finally:
            temp_file.unlink()

    def test_normalize_path_with_multiple_projectid(self, tmp_path):
        """Test normalizing path with multiple projectid files."""
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

        with pytest.raises(MultipleProjectIdError):
            normalize_file_path(test_file, watch_dirs=watch_dirs)


class TestPathNormalizationRelativePath:
    """Test relative path calculation."""

    def test_relative_path_calculation(self):
        """Test that relative path is calculated correctly."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        watch_dirs = [VAST_SRV_DIR.parent]

        normalized = normalize_file_path(test_file, watch_dirs=watch_dirs)

        # Verify relative path can be used to reconstruct absolute path
        reconstructed = normalized.project_root / normalized.relative_path
        assert reconstructed.resolve() == Path(normalized.absolute_path).resolve()

    def test_relative_path_for_root_file(self):
        """Test relative path for file in project root."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        # Find a file in the root of vast_srv
        root_files = [f for f in VAST_SRV_DIR.iterdir() if f.is_file() and f.suffix == ".py"]
        if not root_files:
            pytest.skip("No Python files in vast_srv root")

        test_file = root_files[0]
        watch_dirs = [VAST_SRV_DIR.parent]

        normalized = normalize_file_path(test_file, watch_dirs=watch_dirs)

        # Relative path should be just the filename for root files
        assert normalized.relative_path == test_file.name or normalized.relative_path.startswith(test_file.name)


class TestPathNormalizationPerformance:
    """Test performance of path normalization."""

    def test_normalize_path_performance_large_project(self):
        """Test performance on large project (vast_srv)."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if projectid_file.exists():
            projectid_content = projectid_file.read_text().strip()
            is_old_format = not projectid_content.startswith("{")
            if is_old_format:
                pytest.skip("projectid file is in old format, needs migration to JSON")

        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:100]  # Test first 100 files
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        watch_dirs = [VAST_SRV_DIR.parent]

        import time
        start_time = time.time()

        for test_file in python_files:
            normalized = normalize_file_path(test_file, watch_dirs=watch_dirs)
            assert normalized is not None

        elapsed_time = time.time() - start_time
        # Should complete 100 files in reasonable time (< 10 seconds)
        assert elapsed_time < 10.0, f"Too slow: {elapsed_time:.2f}s for 100 files"

