"""
Tests for project_id validation on real data (DatabaseClient + InProcessRpcClient).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, List, Optional

import pytest

from code_analysis.core.database.files.trash_standalone_support import (
    clear_file_data_via_driver,
    clear_file_vectors_via_driver,
)
from code_analysis.core.database.files.update import update_file_data
from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.exceptions import ProjectIdMismatchError
from code_analysis.core.project_resolution import load_project_info
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


class _ClientFacade:
    """Enough surface for :func:`update_file_data` plus ``add_file`` from :class:`DatabaseClient`."""

    def __init__(self, client: DatabaseClient, driver: SQLiteDriver) -> None:
        self._c = client
        self._driver = driver

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        self._c.execute(sql, params)

    def _commit(self) -> None:
        pass

    def _fetchone(self, sql: str, params: Optional[tuple] = None):
        r = self._c.execute(sql, params)
        rows = r.get("data") or []
        return rows[0] if rows else None

    def _fetchall(self, sql: str, params: Optional[tuple] = None) -> List[dict]:
        r = self._c.execute(sql, params)
        return list(r.get("data") or [])

    def _clear_file_vectors(self, file_id: Any) -> None:
        clear_file_vectors_via_driver(self._driver, str(file_id))

    def clear_file_data(self, file_id: Any) -> None:
        clear_file_data_via_driver(self._driver, str(file_id))


@pytest.fixture
def temp_db(tmp_path: Path) -> Iterator[_ClientFacade]:
    db_path = tmp_path / "test.db"
    driver = create_driver("sqlite", {"path": str(db_path)})
    assert isinstance(driver, SQLiteDriver)
    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=ipc)
    client.connect()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
    try:
        yield _ClientFacade(client, driver)
    finally:
        client.disconnect()


TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
VAST_SRV_DIR = TEST_DATA_DIR / "vast_srv"
BHLFF_DIR = TEST_DATA_DIR / "bhlff"


class TestProjectIdValidationRealData:
    """Test project_id validation on real data from test_data/."""

    def test_validate_on_add_file_matching(self, temp_db: _ClientFacade) -> None:
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

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

        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        file_id = db.add_file(
            path=file_path,
            lines=100,
            last_modified=test_file.stat().st_mtime,
            has_docstring=True,
            project_id=project_id,
        )

        assert file_id

    def test_validate_on_add_file_mismatch(self, temp_db: _ClientFacade) -> None:
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

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

        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (wrong_project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        with pytest.raises(ProjectIdMismatchError) as exc_info:
            db.add_file(
                path=file_path,
                lines=100,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=wrong_project_id,
            )

        assert exc_info.value.file_project_id == correct_project_id
        assert exc_info.value.db_project_id == wrong_project_id

    def test_validate_on_update_file_matching(self, temp_db: _ClientFacade) -> None:
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

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

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )

        file_id = db.add_file(
            path=file_path,
            lines=100,
            last_modified=test_file.stat().st_mtime,
            has_docstring=True,
            project_id=project_id,
        )

        result = update_file_data(db, file_path, project_id, VAST_SRV_DIR)

        if not result.get("success"):
            error = result.get("error", "")
            if "No module named" in error or "mcp_proxy_adapter" in error:
                assert "Project ID mismatch" not in error
                assert result.get("file_id") == file_id
            else:
                assert result.get("success") is True, f"Unexpected error: {error}"
        else:
            assert result.get("success") is True
            assert result.get("file_id") == file_id

    def test_validate_on_update_file_mismatch(self, temp_db: _ClientFacade) -> None:
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

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

        python_files = list(VAST_SRV_DIR.rglob("*.py"))
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        test_file = python_files[0]
        file_path = str(test_file.resolve())

        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (correct_project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )

        db.add_file(
            path=file_path,
            lines=100,
            last_modified=test_file.stat().st_mtime,
            has_docstring=True,
            project_id=correct_project_id,
        )

        with pytest.raises(ProjectIdMismatchError) as exc_info:
            update_file_data(db, file_path, wrong_project_id, VAST_SRV_DIR)

        assert exc_info.value.file_project_id == correct_project_id
        assert exc_info.value.db_project_id == wrong_project_id

    def test_validate_for_vast_srv_files(self, temp_db: _ClientFacade) -> None:
        if not VAST_SRV_DIR.exists():
            pytest.skip("test_data/vast_srv/ not found")

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

        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(VAST_SRV_DIR), VAST_SRV_DIR.name),
        )

        python_files = list(VAST_SRV_DIR.rglob("*.py"))[:5]
        if not python_files:
            pytest.skip("No Python files found in test_data/vast_srv/")

        for test_file in python_files:
            file_path = str(test_file.resolve())
            file_id = db.add_file(
                path=file_path,
                lines=100,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=project_id,
            )
            assert file_id

    def test_validate_for_bhlff_files(self, temp_db: _ClientFacade) -> None:
        if not BHLFF_DIR.exists():
            pytest.skip("test_data/bhlff/ not found")

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

        db._execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, str(BHLFF_DIR), BHLFF_DIR.name),
        )

        python_files = list(BHLFF_DIR.rglob("*.py"))[:3]
        if not python_files:
            pytest.skip("No Python files found in test_data/bhlff/")

        for test_file in python_files:
            file_path = str(test_file.resolve())
            file_id = db.add_file(
                path=file_path,
                lines=100,
                last_modified=test_file.stat().st_mtime,
                has_docstring=True,
                project_id=project_id,
            )
            assert file_id

    def test_validate_missing_projectid_file(self, temp_db: _ClientFacade) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            test_file = root_path / "test.py"
            test_file.write_text("# Test file\n")

            db = temp_db
            project_id = "00000000-0000-0000-0000-000000000000"

            db._execute(
                "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
                (project_id, str(root_path), root_path.name),
            )

            file_id = db.add_file(
                path=str(test_file),
                lines=1,
                last_modified=test_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
            )

            assert file_id

    def test_validate_invalid_projectid_format(self, temp_db: _ClientFacade) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            root_path = Path(tmpdir) / "test_project"
            root_path.mkdir()

            projectid_file = root_path / "projectid"
            projectid_file.write_text("invalid-uuid\n")

            test_file = root_path / "test.py"
            test_file.write_text("# Test file\n")

            db = temp_db
            project_id = "00000000-0000-0000-0000-000000000000"

            db._execute(
                "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
                (project_id, str(root_path), root_path.name),
            )

            file_id = db.add_file(
                path=str(test_file),
                lines=1,
                last_modified=test_file.stat().st_mtime,
                has_docstring=False,
                project_id=project_id,
            )

            assert file_id
