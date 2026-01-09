"""
Tests for project_id validation on real data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
import tempfile
from pathlib import Path
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.exceptions import ProjectIdMismatchError
from code_analysis.core.project_resolution import load_project_id, load_project_info


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


# Get test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestProjectIdValidationRealData:
    """Test project_id validation on real data from test_data/."""

    def test_validate_on_add_file_matching(self, temp_db):
        """Test validation when adding file with matching project_id."""
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

        # Create project and dataset in database first
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        dataset_id = db.get_or_create_dataset(
            project_id=project_id,
            root_path=str(VAST_SRV_DIR),
            name=VAST_SRV_DIR.name,
        )

        # Find a Python file in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        # Add file with correct project_id - should succeed
        file_id = db.add_file(
            path=file_path,
            lines=100,
            last_modified=test_file.stat().st_mtime,
            has_docstring=True,
            project_id=project_id,
            dataset_id=dataset_id,
        )

        assert file_id > 0

    def test_validate_on_add_file_mismatch(self, temp_db):
        """Test validation when adding file with mismatched project_id."""
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
        correct_project_id = project_info.project_id
        wrong_project_id = "00000000-0000-0000-0000-000000000000"

        # Create project and dataset in database first
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (wrong_project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        dataset_id = db.get_or_create_dataset(
            project_id=wrong_project_id,
            root_path=str(VAST_SRV_DIR),
            name=VAST_SRV_DIR.name,
        )

        # Find a Python file in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        # Add file with wrong project_id - should raise ProjectIdMismatchError
        with pytest.raises(ProjectIdMismatchError) as exc_info:
            db.add_file(
                path=file_path,
                lines=100,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=wrong_project_id,
                dataset_id=dataset_id,
            )

        assert exc_info.value.file_project_id == correct_project_id
        assert exc_info.value.db_project_id == wrong_project_id

    def test_validate_on_update_file_matching(self, temp_db):
        """Test validation when updating file with matching project_id."""
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

        # Find a Python file in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        # Create project and dataset in database first
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        dataset_id = db.get_or_create_dataset(
            project_id=project_id,
            root_path=str(VAST_SRV_DIR),
            name=VAST_SRV_DIR.name,
        )

        # First add the file
        file_id = db.add_file(
            path=file_path,
            lines=100,
            last_modified=test_file.stat().st_mtime,
            has_docstring=True,
            project_id=project_id,
            dataset_id=dataset_id,
        )

        # Update file with correct project_id - should succeed
        # Note: This may fail if mcp_proxy_adapter is not available,
        # but project_id validation should still work
        result = db.update_file_data(
            file_path=file_path,
            project_id=project_id,
            root_dir=VAST_SRV_DIR,
        )

        # Check if update succeeded or failed due to missing dependencies
        # The important part is that project_id validation should not raise ProjectIdMismatchError
        if not result.get("success"):
            error = result.get("error", "")
            # If error is about missing module, that's acceptable for this test
            # The test is about project_id validation, not about full file analysis
            if "No module named" in error or "mcp_proxy_adapter" in error:
                # Project ID validation passed (no ProjectIdMismatchError raised)
                # File analysis failed due to missing dependencies, which is acceptable
                assert "Project ID mismatch" not in error
                assert result.get("file_id") == file_id
            else:
                # Other errors should be investigated
                assert result.get("success") is True, f"Unexpected error: {error}"
        else:
            # Update succeeded completely
            assert result.get("success") is True
            assert result.get("file_id") == file_id

    def test_validate_on_update_file_mismatch(self, temp_db):
        """Test validation when updating file with mismatched project_id."""
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
        correct_project_id = project_info.project_id
        wrong_project_id = "00000000-0000-0000-0000-000000000000"

        # Find a Python file in vast_srv
        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        # Create project and dataset in database first (with correct project_id)
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (correct_project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        dataset_id = db.get_or_create_dataset(
            project_id=correct_project_id,
            root_path=str(VAST_SRV_DIR),
            name=VAST_SRV_DIR.name,
        )

        # First add the file with correct project_id
        file_id = db.add_file(
            path=file_path,
            lines=100,
            last_modified=test_file.stat().st_mtime,
            has_docstring=True,
            project_id=correct_project_id,
            dataset_id=dataset_id,
        )

        # Update file with wrong project_id - should raise ProjectIdMismatchError
        with pytest.raises(ProjectIdMismatchError) as exc_info:
            db.update_file_data(
                file_path=file_path,
                project_id=wrong_project_id,
                root_dir=VAST_SRV_DIR,
            )

        assert exc_info.value.file_project_id == correct_project_id
        assert exc_info.value.db_project_id == wrong_project_id

    def test_validate_for_vast_srv_files(self, temp_db):
        """Test validation for multiple files from vast_srv."""
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

        # Create project and dataset in database first
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )
        db._commit()

        dataset_id = db.get_or_create_dataset(
            project_id=project_id,
            root_path=str(VAST_SRV_DIR),
            name=VAST_SRV_DIR.name,
        )

        # Get first 5 Python files
        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:5]
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        # Add all files with correct project_id - should all succeed
        for test_file in python_files:
            file_path = str(test_file.resolve())
            file_id = db.add_file(
                path=file_path,
                lines=100,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=project_id,
                dataset_id=dataset_id,
            )
            assert file_id > 0

    def test_validate_for_bhlff_files(self, temp_db):
        """Test validation for files from bhlff."""
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

        db = temp_db
        project_info = load_project_info(BHLFF_DIR)
        project_id = project_info.project_id

        # Create project and dataset in database first
        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(BHLFF_DIR), BHLFF_DIR.name),
        )
        db._commit()

        dataset_id = db.get_or_create_dataset(
            project_id=project_id,
            root_path=str(BHLFF_DIR),
            name=BHLFF_DIR.name,
        )

        # Get first 3 Python files
        python_files = list(BHLFF_DIR.rglob("*.py"))[:3]
        if not python_files:
            pytest.skip("No Python files found in test_data/bhlff/")

        # Add all files with correct project_id - should all succeed
        for test_file in python_files:
            file_path = str(test_file.resolve())
            file_id = db.add_file(
                path=file_path,
                lines=100,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=project_id,
                dataset_id=dataset_id,
            )
            assert file_id > 0

    def test_validate_missing_projectid_file(self, temp_db):
        """Test validation when projectid file is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            # Create a file without projectid
            test_file = root_path / "test.py"
            test_file.write_text("# Test file\n")

            db = temp_db
            project_id = "00000000-0000-0000-0000-000000000000"

            # Create project in database first
            db._execute(
                "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
                (project_id, str(root_path), root_path.name),
            )
            db._commit()

            # Create dataset
            dataset_id = db.get_or_create_dataset(
                project_id=project_id,
                root_path=str(root_path),
                name=root_path.name,
            )

            # Add file - should not raise error (validation is best-effort)
            # The validation in add_file tries to find projectid, but if not found,
            # it falls back to simple normalization
            file_id = db.add_file(
                path=str(test_file),
                lines=1,
                last_modified=test_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
                dataset_id=dataset_id,
            )

            assert file_id > 0

    def test_validate_invalid_projectid_format(self, temp_db):
        """Test validation with invalid projectid format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            # Create invalid projectid file
            projectid_file = root_path / "projectid"
            projectid_file.write_text("invalid-uuid\n")

            test_file = root_path / "test.py"
            test_file.write_text("# Test file\n")

            db = temp_db
            project_id = "00000000-0000-0000-0000-000000000000"

            # Create project in database first
            db._execute(
                "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
                (project_id, str(root_path), root_path.name),
            )
            db._commit()

            # Create dataset
            dataset_id = db.get_or_create_dataset(
                project_id=project_id,
                root_path=str(root_path),
                name=root_path.name,
            )

            # Add file - should not raise error (validation catches InvalidProjectIdFormatError)
            # and falls back to simple normalization
            file_id = db.add_file(
                path=str(test_file),
                lines=1,
                last_modified=test_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
                dataset_id=dataset_id,
            )

            assert file_id > 0

