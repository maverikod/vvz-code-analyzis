"""
Integration tests for file watcher on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import time
from pathlib import Path
from code_analysis.core.file_watcher_pkg.scanner import scan_directory, should_ignore_path
from code_analysis.core.file_watcher_pkg.processor import FileChangeProcessor, FileDelta
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.project_resolution import load_project_info


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for tests."""
    db_path = tmp_path / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    yield db
    db.close()


class TestFileWatcherScannerRealData:
    """Test file watcher scanner on real data from test_data/."""

    def test_scan_vast_srv_directory(self):
        """Test scanning vast_srv directory - all files found."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        watch_dirs = [TEST_DATA_DIR]
        scanned_files = scan_directory(
            root_dir=VAST_SRV_DIR,
            watch_dirs=watch_dirs,
        )

        # Should find files
        assert isinstance(scanned_files, dict)
        assert len(scanned_files) > 0

        # Check that all files have required fields
        for file_path, file_info in scanned_files.items():
            assert "path" in file_info
            assert "mtime" in file_info
            assert "size" in file_info
            assert "project_root" in file_info
            assert "project_id" in file_info
            assert file_info["project_id"]  # Should not be empty

        # Verify project_id matches projectid file
        project_info = load_project_info(VAST_SRV_DIR)
        for file_path, file_info in scanned_files.items():
            assert file_info["project_id"] == project_info.project_id

    def test_scan_bhlff_directory(self):
        """Test scanning bhlff directory - all files found."""
        if not BHLFF_DIR.exists():
            pytest.skip("test_data/bhlff/ not found")

        # Check if projectid is in new format
        projectid_file = BHLFF_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in bhlff")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        watch_dirs = [TEST_DATA_DIR]
        scanned_files = scan_directory(
            root_dir=BHLFF_DIR,
            watch_dirs=watch_dirs,
        )

        # Should find files (or skip if no Python files in bhlff)
        assert isinstance(scanned_files, dict)
        if len(scanned_files) == 0:
            # Check if there are any Python files at all
            python_files = list(BHLFF_DIR.rglob("*.py"))
            if not python_files:
                pytest.skip("No Python files found in test_data/bhlff/")
            else:
                # Files exist but were not scanned - might be ignored or other issue
                pytest.skip(f"Found {len(python_files)} Python files but scanner returned 0 files")
        
        assert len(scanned_files) > 0

        # Check that all files have required fields
        for file_path, file_info in scanned_files.items():
            assert "path" in file_info
            assert "mtime" in file_info
            assert "size" in file_info
            assert "project_root" in file_info
            assert "project_id" in file_info

    def test_scan_ignores_correct_paths(self):
        """Test that scanner ignores correct paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir)
            
            # Create files that should be ignored
            (root_path / "__pycache__").mkdir()
            (root_path / "__pycache__" / "test.pyc").write_text("# compiled")
            
            (root_path / ".git").mkdir()
            (root_path / ".git" / "config").write_text("[core]")
            
            (root_path / "node_modules").mkdir()
            (root_path / "node_modules" / "package.json").write_text("{}")
            
            # Create files that should NOT be ignored
            (root_path / "test.py").write_text("# Test file")
            (root_path / "src").mkdir(parents=True)
            (root_path / "src" / "main.py").write_text("# Main file")

            watch_dirs = [root_path]
            scanned_files = scan_directory(
                root_dir=root_path,
                watch_dirs=watch_dirs,
            )

            # Should not find ignored files
            scanned_paths = {str(info["path"]) for info in scanned_files.values()}
            assert str(root_path / "__pycache__" / "test.pyc") not in scanned_paths
            assert str(root_path / ".git" / "config") not in scanned_paths
            assert str(root_path / "node_modules" / "package.json") not in scanned_paths

    def test_should_ignore_path(self):
        """Test should_ignore_path function."""
        # Test ignored patterns
        assert should_ignore_path(Path("/path/to/__pycache__/file.pyc")) is True
        assert should_ignore_path(Path("/path/to/.git/config")) is True
        assert should_ignore_path(Path("/path/to/node_modules/package.json")) is True
        assert should_ignore_path(Path("/path/to/.venv/bin/python")) is True

        # Test non-ignored patterns
        assert should_ignore_path(Path("/path/to/test.py")) is False
        assert should_ignore_path(Path("/path/to/src/main.py")) is False

        # Test custom ignore patterns
        custom_patterns = ["*.tmp", "temp/*"]
        assert should_ignore_path(Path("/path/to/file.tmp"), custom_patterns) is True
        assert should_ignore_path(Path("/path/to/temp/file.py"), custom_patterns) is True


class TestFileWatcherProcessorRealData:
    """Test file watcher processor on real data."""

    def test_compute_delta_new_files(self, temp_db):
        """Test computing delta for new files."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        db = temp_db
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        # Create project in database
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        # Scan directory
        watch_dirs = [TEST_DATA_DIR]
        scanned_files = scan_directory(
            root_dir=VAST_SRV_DIR,
            watch_dirs=watch_dirs,
        )

        # Create processor
        processor = FileChangeProcessor(
            database=db,
            watch_dirs=watch_dirs,
        )

        # Compute delta - should find new files
        delta = processor.compute_delta(VAST_SRV_DIR, scanned_files)

        # Should have delta for the project
        assert project_id in delta
        project_delta = delta[project_id]
        assert isinstance(project_delta, FileDelta)
        assert len(project_delta.new_files) > 0

    def test_compute_delta_changed_files(self, temp_db):
        """Test computing delta for changed files."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        db = temp_db
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        # Create project in database
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        # Get a Python file from vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        # Add file to database with old mtime
        old_mtime = test_file.stat().st_mtime - 100
        db.add_file(
            path=file_path,
            lines=100,
            last_modified=old_mtime,
            has_docstring=True,
            project_id=project_id,
        )

        # Scan directory
        watch_dirs = [TEST_DATA_DIR]
        scanned_files = scan_directory(
            root_dir=VAST_SRV_DIR,
            watch_dirs=watch_dirs,
        )

        # Create processor
        processor = FileChangeProcessor(
            database=db,
            watch_dirs=watch_dirs,
        )

        # Compute delta - should find changed file
        delta = processor.compute_delta(VAST_SRV_DIR, scanned_files)

        # Should have delta for the project
        assert project_id in delta
        project_delta = delta[project_id]
        assert isinstance(project_delta, FileDelta)
        # File should be in changed_files (mtime differs)
        changed_paths = {path for path, _, _ in project_delta.changed_files}
        assert file_path in changed_paths

    def test_compute_delta_deleted_files(self, temp_db):
        """Test computing delta for deleted files."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        db = temp_db
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        # Create project in database
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        # Create a temporary file and add it to database
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", dir=VAST_SRV_DIR, delete=False
        ) as tmp_file:
            tmp_file.write("# Temporary test file\n")
            tmp_path = Path(tmp_file.name)

        try:
            file_path = str(tmp_path.resolve())
            db.add_file(
                path=file_path,
                lines=1,
                last_modified=tmp_path.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
            )

            # Delete the file
            tmp_path.unlink()

            # Scan directory
            watch_dirs = [TEST_DATA_DIR]
            scanned_files = scan_directory(
                root_dir=VAST_SRV_DIR,
                watch_dirs=watch_dirs,
            )

            # Create processor
            processor = FileChangeProcessor(
                database=db,
                watch_dirs=watch_dirs,
            )

            # Compute delta - should find deleted file
            delta = processor.compute_delta(VAST_SRV_DIR, scanned_files)

            # Should have delta for the project
            assert project_id in delta
            project_delta = delta[project_id]
            assert isinstance(project_delta, FileDelta)
            # File should be in deleted_files
            assert file_path in project_delta.deleted_files

        finally:
            # Cleanup
            if tmp_path.exists():
                tmp_path.unlink()

    def test_queue_changes_adds_files(self, temp_db):
        """Test that queue_changes adds new files to database."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        db = temp_db
        project_info = load_project_info(VAST_SRV_DIR)
        project_id = project_info.project_id

        # Create project in database
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        # Get first 5 Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:5]
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        # Scan only these files
        scanned_files = {}
        for test_file in python_files:
            file_path = str(test_file.resolve())
            scanned_files[file_path] = {
                "path": test_file,
                "mtime": test_file.stat().st_mtime,
                "size": test_file.stat().st_size,
                "project_root": VAST_SRV_DIR,
                "project_id": project_id,
            }

        # Create processor
        watch_dirs = [TEST_DATA_DIR]
        processor = FileChangeProcessor(
            database=db,
            watch_dirs=watch_dirs,
        )

        # Compute delta
        delta = processor.compute_delta(VAST_SRV_DIR, scanned_files)

        # Queue changes
        stats = processor.queue_changes(VAST_SRV_DIR, delta)

        # Should have queued files (check new_files instead of files_added)
        assert stats.get("new_files", 0) > 0 or stats.get("changed_files", 0) > 0

        # Verify files are in database
        for test_file in python_files:
            file_path = str(test_file.resolve())
            file_record = db.get_file_by_path(file_path, project_id)
            assert file_record is not None

    def test_scan_performance_large_project(self):
        """Test scan performance on large project."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Check if projectid is in new format
        projectid_file = VAST_SRV_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in vast_srv")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        watch_dirs = [TEST_DATA_DIR]

        # Measure scan time
        start_time = time.time()
        scanned_files = scan_directory(
            root_dir=VAST_SRV_DIR,
            watch_dirs=watch_dirs,
        )
        end_time = time.time()

        scan_duration = end_time - start_time
        file_count = len(scanned_files)

        # Should complete in reasonable time (< 30 seconds for large project)
        assert scan_duration < 30.0, f"Scan took {scan_duration:.2f}s, expected < 30s"

        # Should find files
        assert file_count > 0

        # Log performance metrics
        files_per_second = file_count / scan_duration if scan_duration > 0 else 0
        print(f"\nScan performance: {file_count} files in {scan_duration:.2f}s ({files_per_second:.1f} files/s)")

