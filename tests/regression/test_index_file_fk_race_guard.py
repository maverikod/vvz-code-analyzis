"""
Regression tests for index_file RPC: FK-race guard and deterministic error behavior.

Ensures that when indexing is requested for a deleted/missing project we get
deterministic error results (no crash) and no FK exception escapes to the test.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.database_client.protocol import (
    ErrorCode,
    ErrorResult,
    SuccessResult,
)
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

from tests.test_fixture_content import DEFAULT_TEST_FILE_CONTENT


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    """Generate valid UUID4 project ID."""
    return str(uuid.uuid4())


@pytest.fixture
def db_path(temp_dir):
    """Path to test database file."""
    return temp_dir / "test.db"


@pytest.fixture
def seeded_db(temp_dir, db_path, project_id):
    """Create test database with schema and one project; close before yielding (DB file ready)."""
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), temp_dir.name),
    )
    db._commit()
    db.close()


@pytest.fixture
def index_file_handlers(seeded_db, db_path):
    """Create RPC handlers with driver connected to the test DB."""
    driver = create_driver("sqlite", {"path": str(db_path)})
    try:
        handlers = RPCHandlers(driver)
        yield handlers
    finally:
        driver.disconnect()


@pytest.fixture
def valid_project_file(seeded_db, temp_dir, db_path, project_id):
    """Create a real file on disk and a file row with needs_chunking=1; return (file_path, project_id)."""
    import os

    py_file = temp_dir / "test_index.py"
    py_file.write_text(DEFAULT_TEST_FILE_CONTENT, encoding="utf-8")
    driver_config = create_driver_config_for_worker(
        db_path=db_path, driver_type="sqlite"
    )
    db = CodeDatabase(driver_config=driver_config)
    try:
        db.sync_schema()
        file_id = db.add_file(
            path=str(py_file),
            lines=len(DEFAULT_TEST_FILE_CONTENT.splitlines()),
            last_modified=os.path.getmtime(py_file),
            has_docstring=True,
            project_id=project_id,
        )
        db._execute("UPDATE files SET needs_chunking = 1 WHERE id = ?", (file_id,))
        db._commit()
    finally:
        db.close()
    return str(py_file.resolve()), project_id


class TestIndexFileMissingOrInvalidParams:
    """Missing project_id or file_path returns deterministic error (no crash)."""

    def test_index_file_missing_project_id_returns_validation_error(
        self, index_file_handlers, temp_dir
    ):
        """Missing project_id returns VALIDATION_ERROR, no exception."""
        result = index_file_handlers.handle_index_file(
            {"file_path": str(temp_dir / "x.py"), "project_id": ""}
        )
        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR
        assert "file_path" in result.description or "project_id" in result.description

    def test_index_file_missing_file_path_returns_validation_error(
        self, index_file_handlers, project_id
    ):
        """Missing file_path returns VALIDATION_ERROR, no exception."""
        result = index_file_handlers.handle_index_file(
            {"file_path": "", "project_id": project_id}
        )
        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.VALIDATION_ERROR

    def test_index_file_unknown_project_id_returns_deterministic_error(
        self, index_file_handlers, temp_dir
    ):
        """Unknown project_id returns DATABASE_ERROR 'Project not found', no crash."""
        unknown_id = str(uuid.uuid4())
        result = index_file_handlers.handle_index_file(
            {"file_path": str(temp_dir / "any.py"), "project_id": unknown_id}
        )
        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.DATABASE_ERROR
        assert (
            "not found" in result.description.lower() or "Project" in result.description
        )


class TestIndexFileFkDoesNotEscape:
    """FK/IntegrityError during indexing is caught and returned as NOT_FOUND (no top-level exception)."""

    def test_index_file_fk_during_update_returns_not_found_no_exception(
        self, index_file_handlers, valid_project_file
    ):
        """When update_file_data raises IntegrityError, handler returns ErrorResult NOT_FOUND."""
        file_path, project_id = valid_project_file
        mock_db = MagicMock()
        mock_db.update_file_data.side_effect = sqlite3.IntegrityError(
            "FOREIGN KEY constraint failed"
        )
        with patch(
            "code_analysis.core.database.CodeDatabase.from_existing_driver",
            return_value=mock_db,
        ):
            result = index_file_handlers.handle_index_file(
                {"file_path": file_path, "project_id": project_id}
            )
        assert isinstance(result, ErrorResult)
        assert result.error_code == ErrorCode.NOT_FOUND
        assert (
            "no longer exists" in result.description.lower()
            or "deleted" in result.description.lower()
        )


class TestIndexFileValidProjectSucceeds:
    """Valid project and file path still succeed."""

    def test_index_file_valid_project_succeeds(
        self, index_file_handlers, valid_project_file
    ):
        """Valid project_id and file_path return SuccessResult and success in data."""
        file_path, project_id = valid_project_file
        result = index_file_handlers.handle_index_file(
            {"file_path": file_path, "project_id": project_id}
        )
        assert isinstance(result, SuccessResult)
        assert result.data is not None
        assert result.data.get("success") is True

    def test_index_file_first_time_same_mtime_clears_needs_chunking_and_writes_ast(
        self, index_file_handlers, valid_project_file, db_path
    ):
        """Watcher-style row (disk mtime = DB last_modified, no AST) must fully index, not skip."""
        file_path, project_id = valid_project_file
        result = index_file_handlers.handle_index_file(
            {"file_path": file_path, "project_id": project_id}
        )
        assert isinstance(result, SuccessResult)
        assert result.data is not None
        assert result.data.get("skipped") is not True
        driver = create_driver("sqlite", {"path": str(db_path)})
        try:
            r = driver.execute(
                "SELECT f.id, f.needs_chunking FROM files f WHERE f.path = ? AND f.project_id = ?",
                (file_path, project_id),
                None,
            )
            row = (r.get("data") or [{}])[0]
            assert row.get("needs_chunking") in (0, None, False)
            fid = row["id"]
            a = driver.execute(
                "SELECT 1 as ok FROM ast_trees WHERE file_id = ?",
                (fid,),
                None,
            )
            assert len(a.get("data") or []) >= 1
        finally:
            driver.disconnect()
