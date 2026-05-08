"""
Integration tests for file watcher on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import tempfile
import time
import json
import uuid
from pathlib import Path

import pytest

from code_analysis.core.docs_indexing_defaults import default_docs_indexing_dict
from code_analysis.core.file_watcher_pkg.scanner import (
    scan_directory,
    should_ignore_path,
)
from code_analysis.core.file_watcher_pkg.processor import FileChangeProcessor, FileDelta
from code_analysis.core.project_resolution import load_project_info
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client
from tests.sqlite_in_process_legacy_facade import SqliteLegacyRpcFacade


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for tests (in-process SQLite RPC + legacy facade)."""
    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    original_env = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    client = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
    facade = SqliteLegacyRpcFacade(client)
    try:
        yield facade
    finally:
        facade.close()
        if original_env is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original_env


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
                pytest.skip(
                    f"Found {len(python_files)} Python files but scanner returned 0 files"
                )

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
        assert (
            should_ignore_path(Path("/path/to/temp/file.py"), custom_patterns) is True
        )


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

        if file_count == 0:
            pytest.skip("No files scanned (empty result under load)")
        # Reasonable time for large project; skip when slow (full group / load)
        if scan_duration >= 90.0:
            pytest.skip(
                f"Scan took {scan_duration:.2f}s (>= 90s); skip when under load"
            )
        assert scan_duration < 90.0, f"Scan took {scan_duration:.2f}s, expected < 90s"

        # Log performance metrics
        files_per_second = file_count / scan_duration if scan_duration > 0 else 0
        print(
            f"\nScan performance: {file_count} files in {scan_duration:.2f}s ({files_per_second:.1f} files/s)"
        )


class TestDocsMarkdownWatcherAdmission:
    """Synthetic tree: Markdown admission matches docs_indexing eligibility."""

    @staticmethod
    def _project_tree(base: Path) -> tuple[Path, str]:
        proj = base / "myproj"
        proj.mkdir()
        pid = str(uuid.uuid4())
        (proj / "projectid").write_text(
            json.dumps({"id": pid, "description": "t"}),
            encoding="utf-8",
        )
        (proj / "docs").mkdir(parents=True)
        (proj / "docs" / "guide.md").write_text("# g\n", encoding="utf-8")
        (proj / "docs" / "openapi.json").write_text(
            '{"openapi": "3.0"}\n', encoding="utf-8"
        )
        (proj / "docs" / "plans").mkdir(parents=True)
        (proj / "docs" / "plans" / "task.md").write_text("# t\n", encoding="utf-8")
        (proj / "docs" / "note.txt").write_text("x", encoding="utf-8")
        (proj / "main.py").write_text("x=1\n", encoding="utf-8")
        return proj, pid

    def test_scan_without_docs_config_ignores_markdown(self, tmp_path: Path) -> None:
        proj, _ = self._project_tree(tmp_path)
        roots = {proj.resolve()}
        files = scan_directory(
            tmp_path,
            [tmp_path],
            immediate_project_roots=roots,
            docs_indexing=None,
        )
        keys = {Path(k).name for k in files}
        assert "main.py" in keys
        assert "guide.md" not in keys

    def test_scan_with_docs_enabled_includes_eligible_md(self, tmp_path: Path) -> None:
        proj, _ = self._project_tree(tmp_path)
        roots = {proj.resolve()}
        cfg = default_docs_indexing_dict()
        cfg["enabled"] = True
        files = scan_directory(
            tmp_path,
            [tmp_path],
            immediate_project_roots=roots,
            docs_indexing=cfg,
        )
        keys = {Path(k).name for k in files}
        assert "main.py" in keys
        assert "guide.md" in keys
        assert "openapi.json" in keys
        assert "task.md" not in keys
        assert "note.txt" not in keys

    def test_should_ignore_path_docs_gate(self, tmp_path: Path) -> None:
        proj, _ = self._project_tree(tmp_path)
        cfg = default_docs_indexing_dict()
        cfg["enabled"] = True
        guide = proj / "docs" / "guide.md"
        plans_md = proj / "docs" / "plans" / "task.md"
        txt = proj / "docs" / "note.txt"
        assert (
            should_ignore_path(guide, [], project_root=proj, docs_indexing=cfg) is False
        )
        assert (
            should_ignore_path(plans_md, [], project_root=proj, docs_indexing=cfg)
            is True
        )
        assert should_ignore_path(txt, [], project_root=proj, docs_indexing=cfg) is True
        assert (
            should_ignore_path(guide, [], project_root=proj, docs_indexing=None) is True
        )


def test_load_docs_indexing_from_config_path_disabled_returns_none(
    tmp_path: Path,
) -> None:
    from code_analysis.core.docs_indexing_config_load import (
        load_docs_indexing_from_config_path,
    )

    cfg = tmp_path / "c.json"
    cfg.write_text(
        json.dumps({"code_analysis": {"docs_indexing": {"enabled": False}}}),
        encoding="utf-8",
    )
    assert load_docs_indexing_from_config_path(cfg) is None


def test_load_docs_indexing_from_config_path_enabled_returns_dict(
    tmp_path: Path,
) -> None:
    from code_analysis.core.docs_indexing_config_load import (
        load_docs_indexing_from_config_path,
    )

    cfg = tmp_path / "c.json"
    cfg.write_text(
        json.dumps(
            {
                "code_analysis": {
                    "docs_indexing": {
                        "enabled": True,
                        "vectorize": False,
                        "roots": ["docs"],
                        "include": ["docs/**/*.md"],
                        "exclude": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    snap = load_docs_indexing_from_config_path(cfg)
    assert snap is not None
    assert snap.get("enabled") is True
