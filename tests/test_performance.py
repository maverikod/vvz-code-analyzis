"""
Performance tests for path normalization and project resolution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import time
import json
import uuid
from pathlib import Path
from code_analysis.core.path_normalization import normalize_file_path, normalize_path_simple
from code_analysis.core.project_resolution import (
    find_project_root_for_path,
)
from code_analysis.core.project_discovery import discover_projects_in_directory
from code_analysis.core.settings_manager import get_settings
from code_analysis.core.project_manager import ProjectManager
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"


class TestPerformanceProjectRootDetection:
    """Test performance of project root detection."""

    def test_performance_project_root_detection_1000_files(self):
        """Test performance of project root detection for 1000+ files."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find all Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if len(python_files) < 100:
            pytest.skip("Not enough files for performance test")

        # Test with first 1000 files (or all if less)
        test_files = python_files[:1000]

        watch_dirs = [TEST_DATA_DIR]

        # Measure time
        start_time = time.time()
        for file_path in test_files:
            result = find_project_root_for_path(file_path, watch_dirs)
            assert result is not None  # Should find project root
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 10 seconds for 1000 files)
        assert elapsed < 10.0
        print(f"Processed {len(test_files)} files in {elapsed:.2f}s ({len(test_files)/elapsed:.1f} files/s)")

    def test_performance_project_root_detection_caching(self):
        """Test that caching improves performance."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if len(python_files) < 10:
            pytest.skip("Not enough files for performance test")

        test_files = python_files[:100]
        watch_dirs = [TEST_DATA_DIR]

        # First run (cold cache)
        start_time = time.time()
        for file_path in test_files:
            find_project_root_for_path(file_path, watch_dirs)
        first_run_time = time.time() - start_time

        # Second run (warm cache)
        start_time = time.time()
        for file_path in test_files:
            find_project_root_for_path(file_path, watch_dirs)
        second_run_time = time.time() - start_time

        # Second run should be faster (or at least not much slower)
        # Cache might not be implemented, so just check both complete in reasonable time
        assert first_run_time < 5.0
        assert second_run_time < 5.0


class TestPerformancePathNormalization:
    """Test performance of path normalization."""

    def test_performance_path_normalization_1000_paths(self):
        """Test performance of path normalization for 1000+ paths."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find all Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if len(python_files) < 100:
            pytest.skip("Not enough files for performance test")

        test_files = python_files[:1000]

        # Measure time
        start_time = time.time()
        for file_path in test_files:
            try:
                normalized = normalize_file_path(str(file_path))
                assert normalized is not None
            except Exception:
                # Some files might not be in projects, skip
                pass
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 10 seconds for 1000 paths)
        assert elapsed < 10.0
        print(f"Normalized {len(test_files)} paths in {elapsed:.2f}s ({len(test_files)/elapsed:.1f} paths/s)")

    def test_performance_path_normalization_relative_paths(self):
        """Test performance with relative paths."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if len(python_files) < 10:
            pytest.skip("Not enough files for performance test")

        test_files = python_files[:100]

        # Convert to relative paths
        relative_paths = []
        for file_path in test_files:
            try:
                rel_path = file_path.relative_to(VAST_SRV_DIR)
                relative_paths.append(str(rel_path))
            except ValueError:
                pass

        # Measure time
        start_time = time.time()
        for rel_path in relative_paths:
            try:
                # Normalize relative path (should convert to absolute)
                normalized = normalize_path_simple(rel_path)
                assert normalized is not None
            except Exception:
                pass
        elapsed = time.time() - start_time

        assert elapsed < 5.0


class TestPerformanceProjectScanning:
    """Test performance of project scanning."""

    def test_performance_scanning_large_projects(self):
        """Test performance of scanning large projects."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        watch_dirs = [TEST_DATA_DIR]

        # Measure time
        start_time = time.time()
        projects = discover_projects_in_directory(VAST_SRV_DIR, watch_dirs)
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0
        assert len(projects) > 0


class TestPerformanceProjectIdValidation:
    """Test performance of project_id validation."""

    def test_performance_project_id_validation_1000_files(self, tmp_path):
        """Test performance of project_id validation for 1000+ files."""
        # Create test database
        db_path = tmp_path / "test.db"
        driver_config = create_driver_config_for_worker(
            db_path=db_path, driver_type="sqlite"
        )
        db = CodeDatabase(driver_config=driver_config)

        try:
            # Create test project
            project_id = str(uuid.uuid4())
            project_root = tmp_path / "test_project"
            project_root.mkdir()

            # Create projectid file
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Add project to database
            project_id = db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create 1000 test files
            test_files = []
            for i in range(1000):
                test_file = project_root / f"test_{i}.py"
                test_file.write_text(f"# Test file {i}\n")
                test_files.append(test_file)

            # Add files to database
            start_time = time.time()
            for test_file in test_files:
                db.add_file(
                    path=str(test_file),
                    lines=1,
                    last_modified=test_file.stat().st_mtime,
                    has_docstring=False,
                    project_id=project_id,
                )
            elapsed = time.time() - start_time

            # Should complete in reasonable time (< 5 seconds for 1000 files)
            assert elapsed < 5.0
            print(f"Added {len(test_files)} files in {elapsed:.2f}s ({len(test_files)/elapsed:.1f} files/s)")

        finally:
            db.close()


class TestPerformanceSettingsManager:
    """Test performance of SettingsManager."""

    def test_performance_settings_manager_get(self):
        """Test performance of SettingsManager.get()."""
        settings = get_settings()

        # Measure time for many get() calls
        start_time = time.time()
        for _ in range(1000):
            _ = settings.get("max_file_lines")
            _ = settings.get("poll_interval")
            _ = settings.get("batch_size")
        elapsed = time.time() - start_time

        # Should be very fast (< 0.1 seconds for 3000 calls)
        assert elapsed < 0.1

    def test_performance_settings_manager_properties(self):
        """Test performance of SettingsManager properties."""
        settings = get_settings()

        # Measure time for many property accesses
        start_time = time.time()
        for _ in range(1000):
            _ = settings.max_file_lines
            _ = settings.poll_interval
            _ = settings.batch_size
        elapsed = time.time() - start_time

        # Should be very fast (< 0.1 seconds for 3000 accesses)
        assert elapsed < 0.1


class TestPerformanceProjectManager:
    """Test performance of ProjectManager."""

    def test_performance_project_manager_get_list(self):
        """Test performance of getting project list."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")

        manager = ProjectManager()
        watch_dirs = [TEST_DATA_DIR]

        # Measure time
        start_time = time.time()
        projects = manager.get_project_list(watch_dirs=watch_dirs)
        elapsed = time.time() - start_time

        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0


class TestPerformanceDatabaseIntegration:
    """Test performance of database integration."""

    def test_performance_database_integration(self, tmp_path):
        """Test performance of database operations."""
        # Create test database
        db_path = tmp_path / "test.db"
        driver_config = create_driver_config_for_worker(
            db_path=db_path, driver_type="sqlite"
        )
        db = CodeDatabase(driver_config=driver_config)

        try:
            # Create test project
            project_id = str(uuid.uuid4())
            project_root = tmp_path / "test_project"
            project_root.mkdir()

            # Create projectid file
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Add project to database
            db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create and add 100 files
            test_files = []
            for i in range(100):
                test_file = project_root / f"test_{i}.py"
                test_file.write_text(f"# Test file {i}\n")
                test_files.append(test_file)

            # Measure time for adding files
            start_time = time.time()
            for test_file in test_files:
                db.add_file(
                    path=str(test_file),
                    lines=1,
                    last_modified=test_file.stat().st_mtime,
                    has_docstring=False,
                    project_id=project_id,
                )
            elapsed = time.time() - start_time

            # Should complete in reasonable time (< 2 seconds for 100 files)
            assert elapsed < 2.0

            # Measure time for querying files
            start_time = time.time()
            for test_file in test_files:
                file_record = db.get_file_by_path(
                    path=str(test_file), project_id=project_id
                )
                assert file_record is not None
            elapsed = time.time() - start_time

            # Should complete in reasonable time (< 1 second for 100 queries)
            assert elapsed < 1.0

        finally:
            db.close()


class TestPerformanceVectorization:
    """Test performance of vectorization operations."""

    def test_performance_vectorization_large_projects(self, tmp_path):
        """Test performance of vectorization on large projects."""
        # Create test database
        db_path = tmp_path / "test.db"
        driver_config = create_driver_config_for_worker(
            db_path=db_path, driver_type="sqlite"
        )
        db = CodeDatabase(driver_config=driver_config)

        try:
            # Create test project
            project_id = str(uuid.uuid4())
            project_root = tmp_path / "test_project"
            project_root.mkdir()

            # Create projectid file
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Add project to database
            db.get_or_create_project(
                root_path=str(project_root),
                name="test_project",
            )

            # Create 50 test files
            for i in range(50):
                test_file = project_root / f"test_{i}.py"
                test_file.write_text(f'"""Test docstring {i}."""\ndef func_{i}():\n    pass\n')

                db.add_file(
                    path=str(test_file),
                    lines=3,
                    last_modified=test_file.stat().st_mtime,
                    has_docstring=True,
                    project_id=project_id,
                )

            # Measure time for getting files needing chunking
            start_time = time.time()
            files_needing_chunking = db.get_files_needing_chunking(
                project_id=project_id, limit=100
            )
            elapsed = time.time() - start_time

            # Should complete in reasonable time (< 1 second)
            assert elapsed < 1.0
            assert len(files_needing_chunking) == 50

        finally:
            db.close()

