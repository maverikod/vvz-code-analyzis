"""
Tests for relative-path restore behavior in file trash commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.commands.file_management.restore_deleted_files import (
    RestoreDeletedFilesCommand,
)
from code_analysis.commands.file_management.unmark_deleted_file import (
    UnmarkDeletedFileCommand,
)


class _FakeDB:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.calls: list[tuple[str, tuple]] = []

    def get_project(self, project_id: str):  # type: ignore[override]
        return {"id": project_id, "root_path": str(self.project_root)}

    def execute(self, sql: str, params: tuple):  # type: ignore[override]
        self.calls.append((sql, params))
        # Resolve by absolute path only (simulates rows stored as absolute paths)
        rel = "notes/a.py"
        abs_path = str((self.project_root / rel).resolve())
        if "version_dir" in sql:
            if params[1] == abs_path or params[2] == abs_path:
                return {
                    "data": [
                        {
                            "id": 10,
                            "path": "/tmp/trash/p1/notes/a.py",
                            "original_path": abs_path,
                            "version_dir": "/tmp/trash/p1",
                        }
                    ]
                }
            return {"data": []}
        if params[1] == abs_path or params[2] == abs_path:
            return {
                "data": [
                    {
                        "id": 10,
                        "path": "/tmp/trash/p1/notes/a.py",
                        "original_path": abs_path,
                    }
                ]
            }
        return {"data": []}

    def unmark_file_deleted(self, file_path: str, project_id: str) -> bool:  # type: ignore[override]
        return file_path == "notes/a.py" and project_id == "p1"


@pytest.mark.asyncio
async def test_restore_deleted_files_resolves_relative_path(tmp_path: Path) -> None:
    db = _FakeDB(tmp_path)
    cmd = RestoreDeletedFilesCommand(
        database=db,
        project_id="p1",
        file_paths=["notes/a.py"],
        dry_run=False,
    )

    result = await cmd.execute()

    assert result["success"] is True
    assert result["restored_paths"] == [str((tmp_path / "notes/a.py").resolve())]


@pytest.mark.asyncio
async def test_unmark_deleted_file_resolves_relative_path(tmp_path: Path) -> None:
    db = _FakeDB(tmp_path)
    cmd = UnmarkDeletedFileCommand(
        database=db,
        project_id="p1",
        file_path="notes/a.py",
        dry_run=True,
    )

    result = await cmd.execute()

    assert result["restored"] is True
    assert "Would restore file" in result["message"]
