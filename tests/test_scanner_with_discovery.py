"""
Integration tests for scanner with project discovery.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.file_watcher_pkg.scanner import scan_directory, should_skip_dir


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    """Generate valid UUID4 project ID."""
    return str(uuid.uuid4())


def create_projectid_file(project_dir: Path, project_id: str) -> None:
    """Create projectid file in JSON format (required by load_project_info)."""
    projectid_path = project_dir / "projectid"
    projectid_path.write_text(
        json.dumps({"id": project_id, "description": "Test"}),
        encoding="utf-8",
    )


def create_file(directory: Path, filename: str, content: str = "") -> Path:
    """Create a file in directory."""
    file_path = directory / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestScannerWithDiscovery:
    """Integration tests for scanner with project discovery."""

    def test_scan_directory_single_project(self, temp_dir, project_id):
        """Test scanning directory with single project."""
        # Create project
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create files
        file1 = create_file(project_root, "file1.py", "print('hello')")
        file2 = create_file(project_root / "src", "file2.py", "print('world')")

        # Scan directory
        files = scan_directory(temp_dir, [temp_dir])

        # Check results
        assert len(files) == 2
        assert str(file1.resolve()) in files
        assert str(file2.resolve()) in files

        # Check project association
        file1_info = files[str(file1.resolve())]
        assert file1_info["project_id"] == project_id
        assert file1_info["project_root"] == project_root.resolve()

        file2_info = files[str(file2.resolve())]
        assert file2_info["project_id"] == project_id
        assert file2_info["project_root"] == project_root.resolve()

    def test_scan_directory_multiple_projects(self, temp_dir):
        """Test scanning directory with multiple projects."""
        # Create multiple projects
        project1 = temp_dir / "project1"
        project1.mkdir()
        project_id1 = str(uuid.uuid4())
        create_projectid_file(project1, project_id1)

        project2 = temp_dir / "project2"
        project2.mkdir()
        project_id2 = str(uuid.uuid4())
        create_projectid_file(project2, project_id2)

        # Create files in each project
        file1 = create_file(project1, "file1.py", "print('hello')")
        file2 = create_file(project2, "file2.py", "print('world')")

        # Scan directory
        files = scan_directory(temp_dir, [temp_dir])

        # Check results
        assert len(files) == 2

        # Check project associations
        file1_info = files[str(file1.resolve())]
        assert file1_info["project_id"] == project_id1

        file2_info = files[str(file2.resolve())]
        assert file2_info["project_id"] == project_id2

    def test_scan_directory_files_without_project(self, temp_dir, project_id):
        """Test that files without project are skipped."""
        # Create project
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create file in project
        file_in_project = create_file(project_root, "file1.py", "print('hello')")

        # Create directory without project
        no_project_dir = temp_dir / "no_project"
        no_project_dir.mkdir()
        file_no_project = create_file(no_project_dir, "file2.py", "print('world')")

        # Scan directory
        files = scan_directory(temp_dir, [temp_dir])

        # Check results - only file in project should be included
        assert len(files) == 1
        assert str(file_in_project.resolve()) in files
        assert str(file_no_project.resolve()) not in files

    def test_scan_directory_nested_projects_skipped(self, temp_dir):
        """Deeper projectid is ignored; subtree files belong to the immediate-child root."""
        parent_project = temp_dir / "parent"
        parent_project.mkdir()
        parent_id = str(uuid.uuid4())
        create_projectid_file(parent_project, parent_id)

        child_project = parent_project / "child"
        child_project.mkdir()
        create_projectid_file(child_project, str(uuid.uuid4()))

        parent_file = create_file(parent_project, "parent.py", "print('parent')")
        child_file = create_file(child_project, "child.py", "print('child')")

        files = scan_directory(temp_dir, [temp_dir])

        assert str(parent_file.resolve()) in files
        assert str(child_file.resolve()) in files
        assert files[str(child_file.resolve())]["project_root"] == parent_project.resolve()
        assert files[str(child_file.resolve())]["project_id"] == parent_id

    def test_scan_directory_ignores_patterns(self, temp_dir, project_id):
        """Test that ignore patterns work correctly."""
        # Create project
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create files (only .py is in code_file_extensions; .json is excluded by scanner)
        file1 = create_file(project_root, "file1.py", "print('hello')")
        create_file(project_root, "file2.json", '{"key": "value"}')

        # Create file in ignored directory
        ignored_dir = project_root / "__pycache__"
        ignored_file = create_file(ignored_dir, "file.pyc", "compiled")

        # Scan directory
        files = scan_directory(temp_dir, [temp_dir])

        # Check results - code file included, __pycache__ and non-code extensions excluded
        assert str(file1.resolve()) in files
        assert str(ignored_file.resolve()) not in files

    def test_scan_directory_file_metadata(self, temp_dir, project_id):
        """Test that file metadata is correctly captured."""
        # Create project
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create file
        file_path = create_file(project_root, "file1.py", "print('hello')")

        # Scan directory
        files = scan_directory(temp_dir, [temp_dir])

        # Check metadata
        file_info = files[str(file_path.resolve())]
        assert "path" in file_info
        assert "mtime" in file_info
        assert "size" in file_info
        assert "project_root" in file_info
        assert "project_id" in file_info

        assert file_info["path"] == file_path.resolve()
        assert file_info["project_id"] == project_id
        assert file_info["project_root"] == project_root.resolve()
        assert file_info["size"] > 0
        assert file_info["mtime"] > 0

    def test_scan_directory_skips_nested_test_data_mirror(self, temp_dir, project_id):
        """Nested ``project/test_data/...`` must not be traversed (no stray .py)."""
        project_root = temp_dir / "proj"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        create_file(project_root, "ok.py", "x=1")
        nested = project_root / "test_data" / "mirror"
        nested.mkdir(parents=True)
        create_file(nested, "bad.py", "x=2")

        files = scan_directory(temp_dir, [temp_dir])
        assert len(files) == 1
        assert any("ok.py" in k for k in files)
        assert not any("bad.py" in k for k in files)

    def test_scan_directory_skips_data_trash_subtree(self, temp_dir, project_id):
        """``data/trash`` must not be descended into."""
        project_root = temp_dir / "proj"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        create_file(project_root, "ok.py", "x=1")
        trash_py = (
            project_root / "data" / "trash" / "snap" / "gone.py"
        )
        trash_py.parent.mkdir(parents=True)
        trash_py.write_text("x=3", encoding="utf-8")

        files = scan_directory(temp_dir, [temp_dir])
        assert len(files) == 1
        assert not any("gone.py" in k for k in files)

    def test_should_skip_dir_nested_test_data(self, temp_dir):
        root = temp_dir.resolve()
        inner = temp_dir / "a" / "test_data"
        assert should_skip_dir(inner, walk_root=root) is True
        top = temp_dir / "test_data"
        assert should_skip_dir(top, walk_root=root) is False
