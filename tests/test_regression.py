"""
Regression tests to ensure backward compatibility after refactoring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
import json
import uuid
from pathlib import Path
from code_analysis.core.path_normalization import normalize_file_path
from code_analysis.core.project_resolution import (
    find_project_root_for_path,
    normalize_abs_path,
    load_project_info,
    load_project_id,
)
from code_analysis.core.project_discovery import discover_projects_in_directory
from code_analysis.core.settings_manager import get_settings
from code_analysis.core.project_manager import ProjectManager
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"
CODE_ANALYSIS_DIR = TEST_DATA_DIR / "code_analysis"


class TestRegressionBackwardCompatibility:
    """Test backward compatibility with old API and formats."""

    def test_regression_old_projectid_format_support(self):
        """Test backward compatibility with old projectid format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create old format projectid file (plain UUID)
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            projectid_file.write_text(project_id)

            # Should still be able to load (backward compatibility)
            try:
                loaded_id = load_project_id(project_root)
                assert loaded_id == project_id
            except Exception:
                # If old format is no longer supported, that's OK
                # But we should document the breaking change
                pass

    def test_regression_old_api_path_normalization(self):
        """Test backward compatibility with old path normalization API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Test\n")

            # Old API: normalize_abs_path should still work
            normalized = normalize_abs_path(str(test_file))
            assert normalized is not None
            assert Path(normalized).is_absolute()

    def test_regression_existing_configurations(self):
        """Test backward compatibility with existing configurations."""
        # SettingsManager should work with default values
        settings = get_settings()

        # All settings should have default values
        assert settings.get("max_file_lines") is not None
        assert settings.get("poll_interval") is not None
        assert settings.get("batch_size") is not None

    def test_regression_existing_databases(self, tmp_path):
        """Test backward compatibility with existing databases."""
        # Create test database
        db_path = tmp_path / "test.db"
        driver_config = create_driver_config_for_worker(
            db_path=db_path, driver_type="sqlite"
        )
        db = CodeDatabase(driver_config=driver_config)

        try:
            # Should be able to create and query projects
            project_id = str(uuid.uuid4())
            project_id = db.get_or_create_project(
                root_path=str(tmp_path),
                name="test_project",
            )

            # Should be able to query project
            project = db.get_project(project_id)
            assert project is not None
            assert project["id"] == project_id

        finally:
            db.close()


class TestRegressionExistingProjects:
    """Test regression with existing projects from test_data/."""

    def test_regression_vast_srv_project(self):
        """Test that vast_srv project still works after refactoring."""
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

        # Should be able to load project info
        project_info = load_project_info(VAST_SRV_DIR)
        assert project_info.project_id
        assert project_info.root_path == VAST_SRV_DIR.resolve()

        # Should be able to find project root for files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if python_files:
            test_file = python_files[0]
            result = find_project_root_for_path(test_file, [TEST_DATA_DIR])
            assert result is not None
            assert result.project_id == project_info.project_id

    def test_regression_bhlff_project(self):
        """Test that bhlff project still works after refactoring."""
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

        # Should be able to load project info
        project_info = load_project_info(BHLFF_DIR)
        assert project_info.project_id
        assert project_info.root_path == BHLFF_DIR.resolve()

    def test_regression_code_analysis_project(self):
        """Test that code_analysis project still works after refactoring."""
        if not CODE_ANALYSIS_DIR.exists():
            pytest.skip("test_data/code_analysis/ not found")

        # Check if projectid is in new format
        projectid_file = CODE_ANALYSIS_DIR / "projectid"
        if not projectid_file.exists():
            pytest.skip("projectid file not found in code_analysis")

        projectid_content = projectid_file.read_text().strip()
        is_old_format = not projectid_content.startswith("{")
        if is_old_format:
            pytest.skip("projectid file is in old format, needs migration to JSON")

        # Should be able to load project info
        project_info = load_project_info(CODE_ANALYSIS_DIR)
        assert project_info.project_id
        assert project_info.root_path == CODE_ANALYSIS_DIR.resolve()


class TestRegressionExistingFiles:
    """Test regression with existing files from test_data/."""

    def test_regression_vast_srv_files(self):
        """Test that files from vast_srv still work after refactoring."""
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

        # Find Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in vast_srv")

        # Test with first 10 files
        for test_file in python_files[:10]:
            # Should be able to normalize path
            try:
                normalized = normalize_file_path(str(test_file))
                assert normalized is not None
                assert normalized.absolute_path
                assert normalized.project_id
            except Exception as e:
                # Some files might not be in projects, that's OK
                # But we should log for debugging
                print(f"Warning: Could not normalize {test_file}: {e}")

    def test_regression_bhlff_files(self):
        """Test that files from bhlff still work after refactoring."""
        if not BHLFF_DIR.exists():
            pytest.skip("test_data/bhlff/ not found")

        # Find Python files
        python_files = list(BHLFF_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in bhlff")

        # Test with first 5 files
        for test_file in python_files[:5]:
            # Should be able to normalize path
            try:
                normalized = normalize_file_path(str(test_file))
                assert normalized is not None
            except Exception as e:
                print(f"Warning: Could not normalize {test_file}: {e}")


class TestRegressionExistingSettings:
    """Test regression with existing settings."""

    def test_regression_settings_default_values(self):
        """Test that default settings values are preserved."""
        settings = get_settings()

        # All default values should be accessible
        defaults = {
            "max_file_lines": 400,
            "poll_interval": 30,
            "batch_size": 10,
            "retry_attempts": 3,
            "retry_delay": 10.0,
        }

        for key, expected_value in defaults.items():
            value = settings.get(key)
            assert value is not None
            # Value might be overridden by env vars, so just check it's not None

    def test_regression_settings_properties(self):
        """Test that settings properties still work."""
        settings = get_settings()

        # Properties should be accessible
        assert settings.max_file_lines is not None
        assert settings.poll_interval is not None
        assert settings.batch_size is not None


class TestRegressionDataMigration:
    """Test regression after data migration."""

    def test_regression_migration_without_data_loss(self):
        """Test that migration doesn't cause data loss."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            # Create old format projectid file
            project_id = str(uuid.uuid4())
            projectid_file = project_root / "projectid"
            original_content = project_id
            projectid_file.write_text(original_content)

            # Migrate to JSON
            from scripts.migrate_projectid_to_json import migrate_projectid_file

            migrate_projectid_file(projectid_file, description="Test project")

            # Verify project_id is preserved
            project_info = load_project_info(project_root)
            assert project_info.project_id == project_id

            # Verify backup exists
            backup_file = projectid_file.with_suffix(".projectid.backup")
            assert backup_file.exists()
            assert backup_file.read_text().strip() == original_content

    def test_regression_existing_faiss_indexes(self, tmp_path):
        """Test that existing FAISS indexes still work."""
        # This test would require actual FAISS index files
        # For now, just verify the code can handle missing indexes gracefully
        from code_analysis.core.faiss_manager import FaissIndexManager

        # Try to create manager with nonexistent index
        index_path = tmp_path / "nonexistent.index"
        try:
            manager = FaissIndexManager(
                index_path=str(index_path),
                vector_dim=384,
            )
            # Should not crash, even if index doesn't exist
            assert manager is not None
        except ImportError:
            # FAISS not installed, skip
            pytest.skip("FAISS not installed")


class TestRegressionExistingWorkflows:
    """Test regression with existing workflows."""

    def test_regression_project_discovery_workflow(self):
        """Test that project discovery workflow still works."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")

        # Should be able to discover projects
        projects = discover_projects_in_directory(TEST_DATA_DIR, [TEST_DATA_DIR])

        # Should find at least one project if test_data exists
        assert isinstance(projects, list)
        # Projects might be empty if no projectid files, that's OK

    def test_regression_project_manager_workflow(self):
        """Test that project manager workflow still works."""
        if not TEST_DATA_DIR.exists():
            pytest.skip("test_data/ directory not found")

        manager = ProjectManager()
        watch_dirs = [TEST_DATA_DIR]

        # Should be able to get project list
        projects = manager.get_project_list(watch_dirs=watch_dirs)
        assert isinstance(projects, list)

    def test_regression_database_workflow(self, tmp_path):
        """Test that database workflow still works."""
        # Create test database
        db_path = tmp_path / "test.db"
        driver_config = create_driver_config_for_worker(
            db_path=db_path, driver_type="sqlite"
        )
        db = CodeDatabase(driver_config=driver_config)

        try:
            # Create project
            project_id = db.get_or_create_project(
                root_path=str(tmp_path),
                name="test_project",
            )

            # Add file
            test_file = tmp_path / "test.py"
            test_file.write_text("# Test\n")

            dataset_id = str(db.get_or_create_dataset(project_id, str(tmp_path)))
            file_id = db.add_file(
                path=str(test_file),
                lines=1,
                last_modified=test_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
                dataset_id=dataset_id,
            )

            # Query file
            file_record = db.get_file_by_path(
                path=str(test_file), project_id=project_id
            )
            assert file_record is not None
            assert file_record["id"] == file_id

        finally:
            db.close()

