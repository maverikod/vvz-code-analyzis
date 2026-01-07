"""
Tests for project discovery module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.core.project_discovery import (
    DuplicateProjectIdError,
    NestedProjectError,
    ProjectRoot,
    discover_projects_in_directory,
    find_project_root,
    validate_no_nested_projects,
)


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
    """Create projectid file in project directory."""
    projectid_path = project_dir / "projectid"
    projectid_path.write_text(project_id, encoding="utf-8")


def create_file(directory: Path, filename: str, content: str = "") -> Path:
    """Create a file in directory."""
    file_path = directory / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_find_project_root_file_in_root(self, temp_dir, project_id):
        """Test finding project root when file is in project root."""
        # Create project structure
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create file in project root
        file_path = create_file(project_root, "file.py", "print('hello')")

        # Find project root
        result = find_project_root(file_path, [temp_dir])

        assert result is not None
        assert result.project_id == project_id
        assert result.root_path == project_root.resolve()
        assert result.watch_dir == temp_dir.resolve()

    def test_find_project_root_file_in_subdirectory(self, temp_dir, project_id):
        """Test finding project root when file is in subdirectory."""
        # Create project structure
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create file in subdirectory
        subdir = project_root / "src" / "module"
        file_path = create_file(subdir, "file.py", "print('hello')")

        # Find project root
        result = find_project_root(file_path, [temp_dir])

        assert result is not None
        assert result.project_id == project_id
        assert result.root_path == project_root.resolve()

    def test_find_project_root_file_outside_watch_dir(self, temp_dir, project_id):
        """Test that file outside watch_dir returns None."""
        # Create project outside watch_dir
        outside_dir = temp_dir.parent / f"outside_{uuid.uuid4().hex[:8]}"
        outside_dir.mkdir(exist_ok=True)
        try:
            project_root = outside_dir / "project1"
            project_root.mkdir()
            create_projectid_file(project_root, project_id)

            # Create file
            file_path = create_file(project_root, "file.py", "print('hello')")

            # Find project root (should return None)
            result = find_project_root(file_path, [temp_dir])

            assert result is None
        finally:
            # Cleanup
            import shutil
            if outside_dir.exists():
                shutil.rmtree(outside_dir, ignore_errors=True)

    def test_find_project_root_no_projectid(self, temp_dir):
        """Test that file without projectid returns None."""
        # Create directory without projectid
        project_root = temp_dir / "project1"
        project_root.mkdir()

        # Create file
        file_path = create_file(project_root, "file.py", "print('hello')")

        # Find project root (should return None)
        result = find_project_root(file_path, [temp_dir])

        assert result is None

    def test_find_project_root_nested_projects_error(self, temp_dir, project_id):
        """Test that nested projects raise NestedProjectError."""
        # Create parent project
        parent_project = temp_dir / "parent"
        parent_project.mkdir()
        parent_id = str(uuid.uuid4())
        create_projectid_file(parent_project, parent_id)

        # Create child project inside parent
        child_project = parent_project / "child"
        child_project.mkdir()
        create_projectid_file(child_project, project_id)

        # Create file in child project
        file_path = create_file(child_project, "file.py", "print('hello')")

        # Find project root (should raise NestedProjectError)
        with pytest.raises(NestedProjectError) as exc_info:
            find_project_root(file_path, [temp_dir])

        assert exc_info.value.child_project == child_project.resolve()
        assert exc_info.value.parent_project == parent_project.resolve()

    def test_find_project_root_invalid_projectid(self, temp_dir):
        """Test that invalid projectid file is skipped."""
        # Create project with invalid projectid
        project_root = temp_dir / "project1"
        project_root.mkdir()
        projectid_path = project_root / "projectid"
        projectid_path.write_text("invalid-uuid", encoding="utf-8")

        # Create file
        file_path = create_file(project_root, "file.py", "print('hello')")

        # Find project root (should return None due to invalid projectid)
        result = find_project_root(file_path, [temp_dir])

        assert result is None

    def test_find_project_root_multiple_watch_dirs(self, temp_dir, project_id):
        """Test finding project root with multiple watch directories."""
        # Create two watch directories
        watch_dir1 = temp_dir / "watch1"
        watch_dir1.mkdir()
        watch_dir2 = temp_dir / "watch2"
        watch_dir2.mkdir()

        # Create project in watch_dir1
        project_root = watch_dir1 / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Create file
        file_path = create_file(project_root, "file.py", "print('hello')")

        # Find project root
        result = find_project_root(file_path, [watch_dir1, watch_dir2])

        assert result is not None
        assert result.project_id == project_id
        assert result.watch_dir == watch_dir1.resolve()


class TestDiscoverProjectsInDirectory:
    """Tests for discover_projects_in_directory function."""

    def test_discover_single_project(self, temp_dir, project_id):
        """Test discovering single project in watch directory."""
        # Create project
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Discover projects
        projects = discover_projects_in_directory(temp_dir)

        assert len(projects) == 1
        assert projects[0].project_id == project_id
        assert projects[0].root_path == project_root.resolve()
        assert projects[0].watch_dir == temp_dir.resolve()

    def test_discover_multiple_projects(self, temp_dir):
        """Test discovering multiple projects in watch directory."""
        # Create multiple projects
        project_ids = []
        for i in range(3):
            project_root = temp_dir / f"project{i}"
            project_root.mkdir()
            project_id = str(uuid.uuid4())
            project_ids.append(project_id)
            create_projectid_file(project_root, project_id)

        # Discover projects
        projects = discover_projects_in_directory(temp_dir)

        assert len(projects) == 3
        discovered_ids = {p.project_id for p in projects}
        assert discovered_ids == set(project_ids)

    def test_discover_projects_in_subdirectories(self, temp_dir):
        """Test discovering projects in subdirectories."""
        # Create projects at different levels
        project1 = temp_dir / "project1"
        project1.mkdir()
        project_id1 = str(uuid.uuid4())
        create_projectid_file(project1, project_id1)

        project2 = temp_dir / "dir1" / "project2"
        project2.mkdir(parents=True)
        project_id2 = str(uuid.uuid4())
        create_projectid_file(project2, project_id2)

        # Discover projects
        projects = discover_projects_in_directory(temp_dir)

        assert len(projects) == 2
        discovered_ids = {p.project_id for p in projects}
        assert discovered_ids == {project_id1, project_id2}

    def test_discover_projects_nested_error(self, temp_dir):
        """Test that nested projects raise NestedProjectError."""
        # Create parent project
        parent_project = temp_dir / "parent"
        parent_project.mkdir()
        parent_id = str(uuid.uuid4())
        create_projectid_file(parent_project, parent_id)

        # Create child project inside parent
        child_project = parent_project / "child"
        child_project.mkdir()
        child_id = str(uuid.uuid4())
        create_projectid_file(child_project, child_id)

        # Discover projects (should raise NestedProjectError)
        with pytest.raises(NestedProjectError) as exc_info:
            discover_projects_in_directory(temp_dir)

        assert exc_info.value.child_project == child_project.resolve()
        assert exc_info.value.parent_project == parent_project.resolve()

    def test_discover_projects_duplicate_id_error(self, temp_dir):
        """Test that duplicate project_id raises DuplicateProjectIdError."""
        # Create two projects with same ID
        project_id = str(uuid.uuid4())
        project1 = temp_dir / "project1"
        project1.mkdir()
        create_projectid_file(project1, project_id)

        project2 = temp_dir / "project2"
        project2.mkdir()
        create_projectid_file(project2, project_id)

        # Discover projects (should raise DuplicateProjectIdError)
        with pytest.raises(DuplicateProjectIdError) as exc_info:
            discover_projects_in_directory(temp_dir)

        assert exc_info.value.project_id == project_id
        assert exc_info.value.existing_root in {project1.resolve(), project2.resolve()}
        assert exc_info.value.duplicate_root in {project1.resolve(), project2.resolve()}
        assert exc_info.value.existing_root != exc_info.value.duplicate_root

    def test_discover_projects_invalid_projectid_skipped(self, temp_dir, project_id):
        """Test that invalid projectid files are skipped."""
        # Create valid project
        valid_project = temp_dir / "valid"
        valid_project.mkdir()
        create_projectid_file(valid_project, project_id)

        # Create invalid project
        invalid_project = temp_dir / "invalid"
        invalid_project.mkdir()
        projectid_path = invalid_project / "projectid"
        projectid_path.write_text("not-a-uuid", encoding="utf-8")

        # Discover projects (should only find valid one)
        projects = discover_projects_in_directory(temp_dir)

        assert len(projects) == 1
        assert projects[0].project_id == project_id

    def test_discover_projects_empty_directory(self, temp_dir):
        """Test discovering projects in empty directory."""
        projects = discover_projects_in_directory(temp_dir)
        assert len(projects) == 0

    def test_discover_projects_nonexistent_directory(self):
        """Test discovering projects in nonexistent directory."""
        nonexistent = Path("/nonexistent/directory/that/does/not/exist")
        projects = discover_projects_in_directory(nonexistent)
        assert len(projects) == 0

    def test_discover_projects_file_not_directory(self, temp_dir):
        """Test discovering projects when path is a file, not directory."""
        file_path = create_file(temp_dir, "not_a_dir.txt", "content")
        projects = discover_projects_in_directory(file_path)
        assert len(projects) == 0


class TestValidateNoNestedProjects:
    """Tests for validate_no_nested_projects function."""

    def test_validate_no_nested_projects_valid(self, temp_dir, project_id):
        """Test validation when no nested projects exist."""
        # Create single project
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Should not raise
        validate_no_nested_projects(project_root, temp_dir)

    def test_validate_no_nested_projects_nested_error(self, temp_dir):
        """Test validation raises error when nested projects exist."""
        # Create parent project
        parent_project = temp_dir / "parent"
        parent_project.mkdir()
        parent_id = str(uuid.uuid4())
        create_projectid_file(parent_project, parent_id)

        # Create child project
        child_project = parent_project / "child"
        child_project.mkdir()
        child_id = str(uuid.uuid4())
        create_projectid_file(child_project, child_id)

        # Should raise NestedProjectError
        with pytest.raises(NestedProjectError) as exc_info:
            validate_no_nested_projects(child_project, temp_dir)

        assert exc_info.value.child_project == child_project.resolve()
        assert exc_info.value.parent_project == parent_project.resolve()

    def test_validate_no_nested_projects_no_parent(self, temp_dir, project_id):
        """Test validation when project is at watch_dir level."""
        # Create project at watch_dir level
        project_root = temp_dir / "project1"
        project_root.mkdir()
        create_projectid_file(project_root, project_id)

        # Should not raise (no parent projectid)
        validate_no_nested_projects(project_root, temp_dir)


class TestProjectRoot:
    """Tests for ProjectRoot dataclass."""

    def test_project_root_creation(self, temp_dir, project_id):
        """Test creating ProjectRoot object."""
        project_root = temp_dir / "project1"
        project_root.mkdir()

        root = ProjectRoot(
            root_path=project_root,
            project_id=project_id,
            watch_dir=temp_dir,
        )

        assert root.root_path == project_root.resolve()
        assert root.project_id == project_id
        assert root.watch_dir == temp_dir.resolve()

    def test_project_root_immutable(self, temp_dir, project_id):
        """Test that ProjectRoot is immutable (frozen dataclass)."""
        project_root = temp_dir / "project1"
        project_root.mkdir()

        root = ProjectRoot(
            root_path=project_root,
            project_id=project_id,
            watch_dir=temp_dir,
        )

        # Should raise AttributeError when trying to modify
        with pytest.raises(AttributeError):
            root.project_id = "new-id"

