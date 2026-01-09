"""
Tests for projectid migration from old format to JSON format.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import json
import uuid
import shutil
from pathlib import Path
from scripts.migrate_projectid_to_json import (
    migrate_projectid_file,
    find_all_projectid_files,
    migrate_all_projectid_files,
)
from code_analysis.core.exceptions import (
    ProjectIdError,
    InvalidProjectIdFormatError,
)
from code_analysis.core.project_resolution import load_project_info


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"


class TestProjectIdMigration:
    """Test migration of projectid files from old format to JSON."""

    def test_migrate_projectid_file_old_to_json(self):
        """Test migrating projectid file from old format to JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create old format projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(project_id)

            # Migrate
            result = migrate_projectid_file(projectid_file, description="Test project")
            assert result is True

            # Verify JSON format
            content = projectid_file.read_text()
            data = json.loads(content)
            assert data["id"] == project_id
            assert data["description"] == "Test project"

            # Verify backup was created
            backup_file = projectid_file.with_suffix(".projectid.backup")
            assert backup_file.exists()
            assert backup_file.read_text().strip() == project_id

    def test_migrate_projectid_file_already_json(self):
        """Test migrating projectid file that is already in JSON format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create JSON format projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(
                json.dumps({"id": project_id, "description": "Test project"})
            )

            # Migrate (should skip)
            result = migrate_projectid_file(projectid_file, description="New description")
            assert result is False

            # Verify content unchanged
            content = projectid_file.read_text()
            data = json.loads(content)
            assert data["id"] == project_id
            assert data["description"] == "Test project"  # Original description

    def test_migrate_projectid_file_backward_compatibility(self):
        """Test backward compatibility with old format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create old format projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(project_id)

            # Migrate
            migrate_projectid_file(projectid_file)

            # Verify can still load with load_project_info (which supports both formats)
            project_info = load_project_info(project_root)
            assert project_info.project_id == project_id

    def test_migrate_projectid_file_validation_json_format(self):
        """Test validation of JSON format after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create old format projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(project_id)

            # Migrate
            migrate_projectid_file(projectid_file)

            # Verify JSON is valid
            content = projectid_file.read_text()
            data = json.loads(content)  # Should not raise
            assert "id" in data
            assert "description" in data

    def test_migrate_projectid_file_backup_before_migration(self):
        """Test backup is created before migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create old format projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            original_content = project_id
            projectid_file.write_text(original_content)

            # Migrate
            migrate_projectid_file(projectid_file)

            # Verify backup exists and contains original content
            backup_file = projectid_file.with_suffix(".projectid.backup")
            assert backup_file.exists()
            assert backup_file.read_text().strip() == original_content

    def test_migrate_projectid_file_rollback_on_error(self):
        """Test rollback on migration errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "test_project"
            project_root.mkdir()

            # Create invalid projectid file
            projectid_file = project_root / "projectid"
            projectid_file.write_text("invalid-uuid")

            # Migration should raise error
            with pytest.raises(InvalidProjectIdFormatError):
                migrate_projectid_file(projectid_file)

            # File should still exist (not deleted)
            assert projectid_file.exists()

    def test_migrate_all_projectid_files_in_test_data(self):
        """Test migrating all projectid files in test_data/."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")

        # Find all projectid files
        projectid_files = find_all_projectid_files(TEST_DATA_DIR)

        if not projectid_files:
            pytest.skip("No projectid files found in test_data/")

        # Dry run first
        migrated, already_json, errors = migrate_all_projectid_files(
            [TEST_DATA_DIR], description="Migrated from test", dry_run=True
        )

        # Should report what would be migrated
        assert migrated >= 0
        assert already_json >= 0
        assert errors == 0  # Dry run should not have errors

    def test_migrate_all_projectid_files_data_integrity(self):
        """Test data integrity after migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple projects
            for i in range(3):
                project_root = Path(tmpdir) / f"project_{i}"
                project_root.mkdir()

                # Create old format projectid file
                project_id = str(uuid.uuid4())
                projectid_file = project_root / "projectid"
                projectid_file.write_text(project_id)

            # Migrate all
            migrated, already_json, errors = migrate_all_projectid_files(
                [Path(tmpdir)], description="Test migration"
            )

            assert migrated == 3
            assert already_json == 0
            assert errors == 0

            # Verify all files are in JSON format
            for i in range(3):
                project_root = Path(tmpdir) / f"project_{i}"
                projectid_file = project_root / "projectid"
                content = projectid_file.read_text()
                data = json.loads(content)
                assert "id" in data
                assert "description" in data

    def test_migrate_all_projectid_files_performance(self):
        """Test performance of migrating multiple files."""
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create many projects
            num_projects = 20
            for i in range(num_projects):
                project_root = Path(tmpdir) / f"project_{i}"
                project_root.mkdir()

                # Create old format projectid file
                project_id = str(uuid.uuid4())
                projectid_file = project_root / "projectid"
                projectid_file.write_text(project_id)

            # Migrate all and measure time
            start_time = time.time()
            migrated, already_json, errors = migrate_all_projectid_files(
                [Path(tmpdir)], description="Test migration"
            )
            elapsed = time.time() - start_time

            assert migrated == num_projects
            assert errors == 0
            # Should complete in reasonable time (< 1 second for 20 files)
            assert elapsed < 1.0

    def test_migrate_all_projectid_files_error_handling(self):
        """Test error handling during migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create valid project
            project_root1 = Path(tmpdir) / "project_1"
            project_root1.mkdir()
            project_id1 = str(uuid.uuid4())
            (project_root1 / "projectid").write_text(project_id1)

            # Create invalid project
            project_root2 = Path(tmpdir) / "project_2"
            project_root2.mkdir()
            (project_root2 / "projectid").write_text("invalid-uuid")

            # Migrate all - should handle errors gracefully
            migrated, already_json, errors = migrate_all_projectid_files(
                [Path(tmpdir)], description="Test migration"
            )

            # One should migrate, one should error
            assert migrated == 1
            assert errors == 1

    def test_migrate_all_projectid_files_logging(self):
        """Test logging of migration operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            project_id = str(uuid.uuid4())
            (project_root / "projectid").write_text(project_id)

            # Migrate with dry run (should log what would be done)
            migrated, already_json, errors = migrate_all_projectid_files(
                [Path(tmpdir)], description="Test migration", dry_run=True
            )

            assert migrated == 1
            assert errors == 0

    def test_migrate_projectid_file_missing_file(self):
        """Test migration of missing projectid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projectid_file = Path(tmpdir) / "projectid"

            # Should raise error for missing file
            with pytest.raises(ProjectIdError):
                migrate_projectid_file(projectid_file)

    def test_migrate_projectid_file_empty_file(self):
        """Test migration of empty projectid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projectid_file = Path(tmpdir) / "projectid"
            projectid_file.write_text("")

            # Should raise error for empty file
            with pytest.raises(ProjectIdError):
                migrate_projectid_file(projectid_file)

    def test_find_all_projectid_files(self):
        """Test finding all projectid files in directory tree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested projects
            project1 = Path(tmpdir) / "project1"
            project1.mkdir()
            (project1 / "projectid").write_text(str(uuid.uuid4()))

            project2 = Path(tmpdir) / "project2"
            project2.mkdir()
            (project2 / "projectid").write_text(str(uuid.uuid4()))

            nested = project1 / "nested"
            nested.mkdir()
            (nested / "projectid").write_text(str(uuid.uuid4()))

            # Find all
            projectid_files = find_all_projectid_files(Path(tmpdir))

            # Should find all 3
            assert len(projectid_files) == 3
            assert all(f.name == "projectid" for f in projectid_files)

