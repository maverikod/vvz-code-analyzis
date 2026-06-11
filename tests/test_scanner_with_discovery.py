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
        assert (
            files[str(child_file.resolve())]["project_root"] == parent_project.resolve()
        )
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
        trash_py = project_root / "data" / "trash" / "snap" / "gone.py"
        trash_py.parent.mkdir(parents=True)
        trash_py.write_text("x=3", encoding="utf-8")

        files = scan_directory(temp_dir, [temp_dir])
        assert len(files) == 1
        assert not any("gone.py" in k for k in files)

    def test_scan_directory_skips_old_code_subtree(self, temp_dir, project_id):
        """``old_code`` must not be descended into (traversal basename skip)."""
        project_root = temp_dir / "proj"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        create_file(project_root, "ok.py", "x=1")
        backup_py = project_root / "old_code" / "src" / "app.py.bak"
        backup_py.parent.mkdir(parents=True)
        backup_py.write_text("x=3", encoding="utf-8")

        files = scan_directory(temp_dir, [temp_dir])
        assert len(files) == 1
        assert not any("app.py.bak" in k for k in files)

    def test_scan_directory_skips_dot_git_subtree(self, temp_dir, project_id):
        """``.git`` must not be descended into."""
        project_root = temp_dir / "proj"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        create_file(project_root, "ok.py", "x=1")
        git_py = project_root / ".git" / "hooks" / "fake.py"
        git_py.parent.mkdir(parents=True)
        git_py.write_text("x=3", encoding="utf-8")

        files = scan_directory(temp_dir, [temp_dir])
        assert len(files) == 1
        assert not any("fake.py" in k for k in files)

    def test_should_skip_dir_nested_test_data(self, temp_dir):
        root = temp_dir.resolve()
        inner = temp_dir / "a" / "test_data"
        assert should_skip_dir(inner, walk_root=root) is True
        top = temp_dir / "test_data"
        assert should_skip_dir(top, walk_root=root) is True

    def test_should_skip_dir_respects_immediate_project_roots_named_test_data(
        self, temp_dir
    ):
        root = temp_dir.resolve()
        proj = temp_dir / "test_data"
        roots = {proj.resolve()}
        assert (
            should_skip_dir(proj, walk_root=root, immediate_project_roots=roots)
            is False
        )

    def test_should_skip_dir_soft_deleted_project_subtree(self, temp_dir):
        root = temp_dir.resolve()
        dead = (temp_dir / "dead_proj").resolve()
        dead.mkdir()
        soft = {dead}
        assert (
            should_skip_dir(dead, walk_root=root, soft_deleted_project_roots=soft)
            is True
        )
        assert (
            should_skip_dir(
                dead / "pkg", walk_root=root, soft_deleted_project_roots=soft
            )
            is True
        )

    def test_scan_directory_prunes_soft_deleted_project_subtree(
        self, temp_dir, project_id
    ):
        """Paths under ``soft_deleted_project_roots`` are not walked."""
        alive = temp_dir / "alive"
        dead = temp_dir / "dead"
        alive.mkdir()
        dead.mkdir()
        create_projectid_file(alive, project_id)
        create_projectid_file(dead, str(uuid.uuid4()))
        (dead / "gone.py").write_text("x=1", encoding="utf-8")
        (alive / "ok.py").write_text("x=2", encoding="utf-8")
        files = scan_directory(
            temp_dir,
            [temp_dir],
            immediate_project_roots={alive.resolve(), dead.resolve()},
            soft_deleted_project_roots={dead.resolve()},
        )
        assert any("ok.py" in k for k in files)
        assert not any("gone.py" in k for k in files)

    def test_scan_directory_keeps_exception_inside_ignored_dir(
        self, temp_dir, project_id
    ):
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        keep = create_file(project_root / "src" / "generated", "keep.py", "x=1\n")
        blocked = create_file(project_root / "src" / "generated", "b.py", "x=2\n")
        base = create_file(project_root / "src", "a.py", "x=3\n")

        files = scan_directory(
            temp_dir,
            [temp_dir],
            ignore_patterns=["**/src/generated/**"],
            ignore_exception_files={keep.resolve()},
        )

        assert str(keep.resolve()) in files
        assert str(base.resolve()) in files
        assert str(blocked.resolve()) not in files

    def test_scan_directory_keeps_pattern_exception_inside_ignored_dir(
        self, temp_dir, project_id
    ):
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        keep = create_file(project_root / "src" / "generated", "keep.py", "x=1\n")
        blocked = create_file(project_root / "src" / "generated", "b.py", "x=2\n")
        base = create_file(project_root / "src", "a.py", "x=3\n")

        files = scan_directory(
            temp_dir,
            [temp_dir],
            ignore_patterns=["**/src/generated/**"],
            ignore_exception_patterns=["**/src/generated/keep.py"],
        )

        assert str(keep.resolve()) in files
        assert str(base.resolve()) in files
        assert str(blocked.resolve()) not in files

    def test_scan_directory_uses_project_root_for_exception_glob_matching(
        self, temp_dir
    ):
        project1 = temp_dir / "project1"
        project2 = temp_dir / "project2"
        project1.mkdir()
        project2.mkdir()
        create_projectid_file(project1, str(uuid.uuid4()))
        create_projectid_file(project2, str(uuid.uuid4()))

        keep = create_file(project2 / "src" / "generated", "keep.py", "x=1\n")
        blocked = create_file(project2 / "src" / "generated", "drop.py", "x=2\n")
        create_file(project1 / "src" / "generated", "drop.py", "x=3\n")

        files = scan_directory(
            temp_dir,
            [temp_dir],
            ignore_patterns=["**/src/generated/**"],
            ignore_exception_patterns=["**/src/generated/keep.py"],
            immediate_project_roots={project1.resolve(), project2.resolve()},
        )

        assert str(keep.resolve()) in files
        assert str(blocked.resolve()) not in files

    def test_scan_directory_skips_dot_venv_site_packages_without_allowlist(
        self, temp_dir, project_id
    ):
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        app = create_file(project_root / "src", "app.py", "x=1\n")
        vpy = (
            project_root
            / ".venv"
            / "lib"
            / "python3.12"
            / "site-packages"
            / "pkg"
            / "mod.py"
        )
        vpy.parent.mkdir(parents=True)
        vpy.write_text("y=1\n", encoding="utf-8")

        files = scan_directory(temp_dir, [temp_dir])
        assert str(app.resolve()) in files
        assert str(vpy.resolve()) not in files

    def test_scan_directory_merges_allowlisted_venv_record_without_walking_venv(
        self, temp_dir, project_id
    ):
        from code_analysis.core.venv_path_policy import (
            build_allowlisted_site_packages_py_files,
        )

        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        app = create_file(project_root / "src", "app.py", "x=1\n")
        sp = project_root / ".venv" / "lib" / "python3.12" / "site-packages"
        sp.mkdir(parents=True)
        pkg_dir = sp / "mypkg"
        pkg_dir.mkdir()
        mod = pkg_dir / "mod.py"
        mod.write_text("z=1\n", encoding="utf-8")
        dist = sp / "mypkg-1.0.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text("Name: mypkg\nVersion: 1.0\n")
        (dist / "RECORD").write_text("mypkg/mod.py,sha256=abc,12\n", encoding="utf-8")

        allowed = build_allowlisted_site_packages_py_files(project_root, ["mypkg"])
        files = scan_directory(
            temp_dir,
            [temp_dir],
            allowed_venv_py_files=allowed,
        )
        assert str(app.resolve()) in files
        assert str(mod.resolve()) in files
        other = sp / "otherpkg" / "noise.py"
        other.parent.mkdir()
        other.write_text("n=1\n")
        assert str(other.resolve()) not in files

    def test_scan_directory_merge_drops_venv_ignore_exception_without_allowlist(
        self, temp_dir: Path, project_id: str
    ) -> None:
        """Merge must not pull ``ignore_exceptions`` targets from venv without allowlist."""
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        app = create_file(project_root / "src", "app.py", "x=1\n")
        vpy = (
            project_root
            / ".venv"
            / "lib"
            / "python3.12"
            / "site-packages"
            / "pkg"
            / "unlisted.py"
        )
        vpy.parent.mkdir(parents=True)
        vpy.write_text("y=1\n", encoding="utf-8")

        files = scan_directory(
            temp_dir,
            [temp_dir],
            ignore_exception_files={vpy.resolve()},
            immediate_project_roots={project_root.resolve()},
        )
        assert str(app.resolve()) in files
        assert str(vpy.resolve()) not in files

    def test_scan_directory_three_projects_no_venv_files(self, temp_dir: Path) -> None:
        """Regression: multiple project roots under one watch dir must not index .venv."""
        for name in ("mcp_proxy_adapter", "vast_srv", "code_analysis"):
            pr = temp_dir / name
            pr.mkdir()
            create_projectid_file(pr, str(uuid.uuid4()))
            create_file(pr / "src", "app.py", "x=1\n")
            vpy = pr / ".venv" / "lib" / "python3.12" / "site-packages" / "x.py"
            vpy.parent.mkdir(parents=True)
            vpy.write_text("#\n")

        files = scan_directory(temp_dir, [temp_dir])
        assert len(files) == 3
        for k in files:
            assert ".venv" not in k

    def test_scan_watch_dir_does_not_walk_non_project_siblings(
        self, temp_dir, project_id, monkeypatch
    ):
        """Immediate children without projectid must not be entered at all."""
        import os

        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)
        create_file(project_root, "in_project.py", "x=1")

        junk = temp_dir / "not_a_project"
        junk.mkdir()
        deep = junk / "deep" / "tree"
        deep.mkdir(parents=True)
        create_file(deep, "outside.py", "x=2")

        walk_roots: list[str] = []
        orig_walk = os.walk

        def tracked_walk(top, *args, **kwargs):
            walk_roots.append(str(Path(top).resolve()))
            return orig_walk(top, *args, **kwargs)

        monkeypatch.setattr(os, "walk", tracked_walk)

        files = scan_directory(temp_dir, [temp_dir])

        assert len(files) == 1
        assert str((project_root / "in_project.py").resolve()) in files
        junk_res = str(junk.resolve())
        assert not any(
            root == junk_res or root.startswith(junk_res + "/") for root in walk_roots
        )
        assert any(root == str(project_root.resolve()) for root in walk_roots)
