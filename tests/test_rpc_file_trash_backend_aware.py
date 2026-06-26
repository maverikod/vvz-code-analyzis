"""
Tests for backend-aware file trash RPC handlers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from code_analysis.commands.file_management.cleanup_deleted_files import (
    CleanupDeletedFilesCommand,
)
from code_analysis.core.database_client.protocol import DataResult, SuccessResult
from code_analysis.core.database_driver_pkg.rpc_handlers_file_trash import (
    _RPCHandlersFileTrashMixin,
)


class _Handler(_RPCHandlersFileTrashMixin):
    """Represent Handler."""

    def __init__(self, driver: object) -> None:
        """Initialize the instance."""
        self.driver = driver


def test_mark_file_deleted_passes_driver_to_standalone(monkeypatch) -> None:
    """Verify test mark file deleted passes driver to standalone."""
    calls: list[object] = []

    def _fake_via_driver(driver: object, **kwargs: Any) -> bool:
        """Return fake via driver."""
        calls.append(driver)
        del kwargs
        return True

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "mark_file_deleted_via_driver",
        _fake_via_driver,
    )
    driver = object()
    handler = _Handler(driver)

    result = handler.handle_mark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt", "trash_dir": "/tmp/trash"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert calls == [driver]


def test_get_deleted_files_returns_data_result(monkeypatch) -> None:
    """Verify test get deleted files returns data result."""

    def _fake_get_deleted(driver: object, project_id: str) -> list[Dict[str, Any]]:
        """Return fake get deleted."""
        del driver
        return [{"id": 1, "path": "/tmp/trash/p1/a.txt", "project_id": project_id}]

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "get_deleted_files_via_driver",
        _fake_get_deleted,
    )
    handler = _Handler(object())

    result = handler.handle_get_deleted_files({"project_id": "p1"})

    assert isinstance(result, DataResult)
    assert result.data and result.data[0]["id"] == 1


def test_unmark_file_deleted_returns_success(monkeypatch) -> None:
    """Verify test unmark file deleted returns success."""

    def _fake_unmark(
        driver: object,
        file_path: str,
        project_id: str,
        out_error: Dict[str, str] | None = None,
    ) -> bool:
        """Return fake unmark."""
        del driver, out_error
        return file_path == "notes/a.txt" and project_id == "p1"

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "unmark_file_deleted_via_driver",
        _fake_unmark,
    )
    handler = _Handler(object())

    result = handler.handle_unmark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}


def test_cleanup_deleted_files_dry_run_with_client_without_db_path() -> None:
    """Verify test cleanup deleted files dry run with client without db path."""

    class _FakeClient:
        """Represent FakeClient."""

        def get_deleted_files(self, project_id: str) -> list[Dict[str, Any]]:
            """Return get deleted files."""
            return [
                {
                    "id": 10,
                    "path": "/tmp/trash/p1/a.txt",
                    "version_dir": "/tmp/trash/p1",
                    "updated_at": 0,
                }
            ]

    cmd = CleanupDeletedFilesCommand(
        database=_FakeClient(),
        project_id="p1",
        dry_run=True,
        hard_delete=False,
    )
    result = __import__("asyncio").run(cmd.execute())

    assert "error" not in result
    assert result["dry_run"] is True
    assert result["total_files"] == 1


def test_mark_file_deleted_with_sqlite_like_driver(monkeypatch) -> None:
    """Verify test mark file deleted with sqlite like driver."""

    class _SQLiteLikeDriver:
        """Represent SQLiteLikeDriver."""

        db_path = "/tmp/code_analysis.db"

    captured: list[object] = []

    def _capture(driver: object, **kwargs: Any) -> bool:
        """Return capture."""
        captured.append(driver)
        del kwargs
        return True

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "mark_file_deleted_via_driver",
        _capture,
    )
    driver = _SQLiteLikeDriver()
    handler = _Handler(driver)

    result = handler.handle_mark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt", "trash_dir": "/tmp/trash"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert captured == [driver]


def test_hard_delete_file_accepts_uuid_string(monkeypatch) -> None:
    """Verify test hard delete file accepts uuid string."""
    captured: list[object] = []

    def _fake_hard(driver: object, file_id: object) -> None:
        """Return fake hard."""
        captured.append(file_id)

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "hard_delete_file_via_driver",
        _fake_hard,
    )
    handler = _Handler(object())
    fid = "550e8400-e29b-41d4-a716-446655440000"
    result = handler.handle_hard_delete_file({"file_id": fid})

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert captured == [fid]


def test_hard_delete_file_still_accepts_int(monkeypatch) -> None:
    """Verify test hard delete file still accepts int."""
    captured: list[object] = []

    def _fake_hard(driver: object, file_id: object) -> None:
        """Return fake hard."""
        captured.append(file_id)

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "hard_delete_file_via_driver",
        _fake_hard,
    )
    handler = _Handler(object())
    result = handler.handle_hard_delete_file({"file_id": 42})

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert captured == [42]


def test_missing_trash_file_returns_structured_error(monkeypatch) -> None:
    """Verify test missing trash file returns structured error."""

    def _fake_unmark(
        driver: object,
        file_path: str,
        project_id: str,
        out_error: Dict[str, str] | None = None,
    ) -> bool:
        """Return fake unmark."""
        del driver, file_path, project_id
        if out_error is not None:
            out_error["error_code"] = "TRASH_FILE_NOT_FOUND"
            out_error["message"] = "Trash file is missing at /tmp/trash/p1/a.txt"
        return False

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.rpc_handlers_file_trash."
        "unmark_file_deleted_via_driver",
        _fake_unmark,
    )
    handler = _Handler(object())

    result = handler.handle_unmark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {
        "success": False,
        "error_code": "TRASH_FILE_NOT_FOUND",
        "message": "Trash file is missing at /tmp/trash/p1/a.txt",
    }
