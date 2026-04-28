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
    def __init__(self, driver: object) -> None:
        self.driver = driver


def test_mark_file_deleted_without_db_path_uses_existing_driver(monkeypatch) -> None:
    class _FakeDB:
        def mark_file_deleted(self, **kwargs: Any) -> bool:
            return True

    calls: list[object] = []

    def _fake_from_existing_driver(driver: object) -> _FakeDB:
        calls.append(driver)
        return _FakeDB()

    from code_analysis.core.database import CodeDatabase

    monkeypatch.setattr(
        CodeDatabase, "from_existing_driver", _fake_from_existing_driver
    )
    driver = object()  # No db_path attribute (PostgreSQL-like)
    handler = _Handler(driver)

    result = handler.handle_mark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt", "trash_dir": "/tmp/trash"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert calls == [driver]


def test_get_deleted_files_without_db_path_returns_data_result(monkeypatch) -> None:
    class _FakeDB:
        def get_deleted_files(self, project_id: str) -> list[Dict[str, Any]]:
            return [{"id": 1, "path": "/tmp/trash/p1/a.txt", "project_id": project_id}]

    from code_analysis.core.database import CodeDatabase

    monkeypatch.setattr(CodeDatabase, "from_existing_driver", lambda _driver: _FakeDB())
    handler = _Handler(object())  # No db_path attribute

    result = handler.handle_get_deleted_files({"project_id": "p1"})

    assert isinstance(result, DataResult)
    assert result.data and result.data[0]["id"] == 1


def test_unmark_file_deleted_without_db_path_returns_success(monkeypatch) -> None:
    class _FakeDB:
        def unmark_file_deleted(
            self,
            file_path: str,
            project_id: str,
            out_error: Dict[str, str] | None = None,
        ) -> bool:
            return file_path == "notes/a.txt" and project_id == "p1"

    from code_analysis.core.database import CodeDatabase

    monkeypatch.setattr(CodeDatabase, "from_existing_driver", lambda _driver: _FakeDB())
    handler = _Handler(object())  # No db_path attribute

    result = handler.handle_unmark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}


def test_cleanup_deleted_files_dry_run_with_client_without_db_path() -> None:
    class _FakeClient:
        # Intentionally no db_path attribute
        def get_deleted_files(self, project_id: str) -> list[Dict[str, Any]]:
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


def test_sqlite_driver_compatibility_still_uses_from_existing_driver(
    monkeypatch,
) -> None:
    class _FakeDB:
        def mark_file_deleted(self, **kwargs: Any) -> bool:
            return True

    class _SQLiteLikeDriver:
        db_path = "/tmp/code_analysis.db"

    captured: list[object] = []
    from code_analysis.core.database import CodeDatabase

    def _capture(driver: object) -> _FakeDB:
        captured.append(driver)
        return _FakeDB()

    monkeypatch.setattr(CodeDatabase, "from_existing_driver", _capture)
    driver = _SQLiteLikeDriver()
    handler = _Handler(driver)

    result = handler.handle_mark_file_deleted(
        {"project_id": "p1", "file_path": "notes/a.txt", "trash_dir": "/tmp/trash"}
    )

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert captured == [driver]


def test_hard_delete_file_accepts_uuid_string(monkeypatch) -> None:
    captured: list[object] = []

    class _FakeDB:
        def hard_delete_file(self, file_id: object) -> None:
            captured.append(file_id)

    from code_analysis.core.database import CodeDatabase

    monkeypatch.setattr(CodeDatabase, "from_existing_driver", lambda _driver: _FakeDB())
    handler = _Handler(object())
    fid = "550e8400-e29b-41d4-a716-446655440000"
    result = handler.handle_hard_delete_file({"file_id": fid})

    assert isinstance(result, SuccessResult)
    assert result.data == {"success": True}
    assert captured == [fid]


def test_hard_delete_file_still_accepts_int(monkeypatch) -> None:
    captured: list[object] = []

    class _FakeDB:
        def hard_delete_file(self, file_id: object) -> None:
            captured.append(file_id)

    from code_analysis.core.database import CodeDatabase

    monkeypatch.setattr(CodeDatabase, "from_existing_driver", lambda _driver: _FakeDB())
    handler = _Handler(object())
    result = handler.handle_hard_delete_file({"file_id": 42})

    assert isinstance(result, SuccessResult)
    assert captured == [42]


def test_missing_trash_file_returns_structured_error(monkeypatch) -> None:
    class _FakeDB:
        def unmark_file_deleted(
            self,
            file_path: str,
            project_id: str,
            out_error: Dict[str, str] | None = None,
        ) -> bool:
            if out_error is not None:
                out_error["error_code"] = "TRASH_FILE_NOT_FOUND"
                out_error["message"] = "Trash file is missing at /tmp/trash/p1/a.txt"
            return False

    from code_analysis.core.database import CodeDatabase

    monkeypatch.setattr(CodeDatabase, "from_existing_driver", lambda _driver: _FakeDB())
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
