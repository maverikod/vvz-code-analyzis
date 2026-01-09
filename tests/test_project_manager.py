"""
Tests for project manager on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from code_analysis.core.project_manager import ProjectManager
from code_analysis.core.project_resolution import ProjectInfo, load_project_info
from code_analysis.core.exceptions import (
    ProjectIdError,
    ProjectNotFoundError,
    GitOperationError,
)


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"
CODE_ANALYSIS_DIR = TEST_DATA_DIR / "code_analysis"


class TestProjectManagerRealData:
    """Test project manager on real data from test_data/."""

    def test_get_project_list_from_test_data(self):
        """Test getting list of projects from test_data/."""
        manager = ProjectManager()
        watch_dirs = [TEST_DATA_DIR]

        projects = manager.get_project_list(watch_dirs=watch_dirs)

        # Should find at least one project if test_data exists
        if TEST_DATA_DIR.exists():
            assert isinstance(projects, list)
            # Check that all items are ProjectInfo
            for project in projects:
                assert isinstance(project, ProjectInfo)
                assert project.project_id
                assert project.root_path.exists()
                assert (project.root_path / "projectid").exists()

    def test_get_project_info_from_vast_srv(self):
        """Test getting project info for vast_srv project."""
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

        # Load project info directly
        project_info = load_project_info(VAST_SRV_DIR)
        assert project_info.project_id
        assert project_info.root_path == VAST_SRV_DIR.resolve()

        # Test manager
        manager = ProjectManager()
        # Note: get_project_info requires database or will raise ProjectNotFoundError
        # So we test that it raises the expected error
        with pytest.raises(ProjectNotFoundError):
            manager.get_project_info(project_info.project_id)

    def test_create_project_with_description(self):
        """Test creating a new project with description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            manager = ProjectManager()
            description = "Test project for unit testing"
            project_info = manager.create_project(
                root_path=root_path, description=description
            )

            assert isinstance(project_info, ProjectInfo)
            assert project_info.project_id
            assert project_info.description == description
            assert project_info.root_path == root_path.resolve()

            # Verify projectid file exists and has correct format
            projectid_file = root_path / "projectid"
            assert projectid_file.exists()

            # Verify it can be loaded
            loaded_info = load_project_info(root_path)
            assert loaded_info.project_id == project_info.project_id
            assert loaded_info.description == description

    def test_create_project_without_description(self):
        """Test creating a new project without description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            manager = ProjectManager()
            project_info = manager.create_project(root_path=root_path)

            assert isinstance(project_info, ProjectInfo)
            assert project_info.project_id
            assert project_info.description  # Should have default description
            assert project_info.root_path == root_path.resolve()

    def test_create_project_already_exists(self):
        """Test creating a project that already exists."""
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

        manager = ProjectManager()
        existing_info = load_project_info(VAST_SRV_DIR)

        # Should return existing project info
        created_info = manager.create_project(
            root_path=VAST_SRV_DIR, description="New description"
        )

        assert created_info.project_id == existing_info.project_id
        assert created_info.root_path == existing_info.root_path

    def test_create_project_with_git(self):
        """Test creating a project with git initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            manager = ProjectManager()
            description = "Test project with git"
            project_info = manager.create_project(
                root_path=root_path, description=description, init_git=True
            )

            assert isinstance(project_info, ProjectInfo)

            # Check if git was initialized (may skip if git not available)
            git_dir = root_path / ".git"
            if git_dir.exists():
                # Verify .gitignore was created
                gitignore_file = root_path / ".gitignore"
                assert gitignore_file.exists()

                # Verify projectid is in git (should be staged)
                # Note: We can't easily check if files are staged without git commands
                # But we can verify the files exist

    def test_create_project_without_git_when_unavailable(self):
        """Test creating a project when git is not available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            manager = ProjectManager()
            # Should not fail even if git is not available
            project_info = manager.create_project(
                root_path=root_path, description="Test", init_git=True
            )

            assert isinstance(project_info, ProjectInfo)
            # Project should still be created even if git init fails

    def test_validate_project_id_correct(self):
        """Test validating project_id that matches projectid file."""
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

        manager = ProjectManager()
        project_info = load_project_info(VAST_SRV_DIR)

        # Should return True for correct project_id
        result = manager.validate_project_id(VAST_SRV_DIR, project_info.project_id)
        assert result is True

    def test_validate_project_id_incorrect(self):
        """Test validating project_id that does not match projectid file."""
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

        manager = ProjectManager()
        wrong_project_id = "00000000-0000-0000-0000-000000000000"

        # Should return False for incorrect project_id
        result = manager.validate_project_id(VAST_SRV_DIR, wrong_project_id)
        assert result is False

    def test_validate_project_id_missing_file(self):
        """Test validating project_id when projectid file is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            manager = ProjectManager()
            project_id = "00000000-0000-0000-0000-000000000000"

            # Should return False when projectid file is missing
            # validate_project_id catches ProjectIdError and InvalidProjectIdFormatError
            # and returns False
            result = manager.validate_project_id(root_path, project_id)
            assert result is False

    def test_synchronization_with_filesystem(self):
        """Test that project manager synchronizes with filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            manager = ProjectManager()
            description = "Test project for sync"
            project_info = manager.create_project(
                root_path=root_path, description=description
            )

            # Verify project can be discovered from filesystem
            watch_dirs = [Path(tmpdir)]
            projects = manager.get_project_list(watch_dirs=watch_dirs)

            # Should find the created project
            found = False
            for project in projects:
                if project.project_id == project_info.project_id:
                    found = True
                    assert project.description == description
                    break

            assert found, "Created project should be discoverable from filesystem"

