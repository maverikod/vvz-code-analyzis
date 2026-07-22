"""
Tests for delete fallback behavior when DB indexing lags watcher updates.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, cast

import pytest

from code_analysis.commands.file_management.mark_file_deleted import (
    MarkFileDeletedCommand,
)


@pytest.fixture(autouse=True)
def _patch_get_project_to_fake_db_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route domain free-function call sites back to ``_FakeDB`` bound methods.

    ``MarkFileDeletedCommand`` calls the driver-direct free functions (stage-2
    layer collapse: ``get_project`` from the "projects" pass, ``get_file_by_path``
    and ``add_file`` from the "files" pass), which read through
    ``driver.select``/``driver.execute`` - primitives this lightweight test
    double does not implement. Every test in this module supplies its own
    ``get_project``/``get_file_by_path``/``add_file`` shortcuts instead, so
    redirect the call sites to them rather than reimplementing SQL primitives
    on the fake. ``get_file_by_path`` and ``add_file`` are patched both at the
    ``mark_file_deleted`` import site (the command's own direct calls) and at
    the ``domain.files`` import site (the internal ``get_project`` lookup and
    the recursive ``get_file_by_path`` call ``add_file`` makes internally).
    """
    monkeypatch.setattr(
        "code_analysis.commands.file_management.mark_file_deleted.get_project",
        lambda driver, project_id: driver.get_project(project_id),
    )
    monkeypatch.setattr(
        "code_analysis.commands.file_management.mark_file_deleted.get_file_by_path",
        lambda driver, path, project_id, include_deleted=False: driver.get_file_by_path(
            path, project_id, include_deleted=include_deleted
        ),
    )
    monkeypatch.setattr(
        "code_analysis.commands.file_management.mark_file_deleted.add_file",
        lambda driver, path, lines, last_modified, has_docstring, project_id: driver.add_file(
            path=path,
            lines=lines,
            last_modified=last_modified,
            has_docstring=has_docstring,
            project_id=project_id,
        ),
    )
    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.domain.files.get_project",
        lambda driver, project_id: driver.get_project(project_id),
    )
    monkeypatch.setattr(
        "code_analysis.commands.file_management.mark_file_deleted."
        "mark_file_deleted_via_driver",
        lambda driver, file_path, project_id, version_dir=None, reason=None, trash_dir=None: (
            driver.mark_file_deleted(
                file_path=file_path,
                project_id=project_id,
                version_dir=version_dir,
                reason=reason,
                trash_dir=trash_dir,
            )
        ),
    )


class _FakeDB:
    """Represent FakeDB."""

    def __init__(self, project_id: str, project_root: Path, trash_root: Path) -> None:
        """Initialize the instance."""
        self.project_id = project_id
        self.project_root = project_root
        self.trash_root = trash_root
        self._next_id = 1
        self.files_by_abs_path: Dict[str, Dict[str, Any]] = {}
        self.deleted_rows: list[Dict[str, Any]] = []
        # PostgreSQL-like fake: intentionally no db_path attribute.

    def get_project(self, pid: str) -> Optional[Dict[str, str]]:
        """Return get project."""
        if pid != self.project_id:
            return None
        return {"id": self.project_id, "root_path": str(self.project_root)}

    def get_file_by_path(
        self, path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Return get file by path."""
        if project_id != self.project_id:
            return None
        row = self.files_by_abs_path.get(str(Path(path).resolve()))
        if not row:
            return None
        if row.get("deleted") and not include_deleted:
            return None
        return row

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> int:
        """Return add file."""
        abs_path = str(Path(path).resolve())
        if project_id != self.project_id:
            raise ValueError("Project mismatch")
        existing = self.files_by_abs_path.get(abs_path)
        if existing:
            existing.update(
                {
                    "lines": lines,
                    "last_modified": last_modified,
                    "has_docstring": has_docstring,
                    "deleted": 0,
                }
            )
            return int(existing["id"])
        file_id = self._next_id
        self._next_id += 1
        self.files_by_abs_path[abs_path] = {
            "id": file_id,
            "project_id": project_id,
            "path": abs_path,
            "deleted": 0,
            "lines": lines,
            "last_modified": last_modified,
            "has_docstring": has_docstring,
            "original_path": None,
            "version_dir": None,
        }
        return file_id

    def mark_file_deleted(
        self,
        file_path: str,
        project_id: str,
        version_dir: Optional[str] = None,
        reason: Optional[str] = None,
        trash_dir: Optional[str] = None,
    ) -> bool:
        """Return mark file deleted."""
        del reason, version_dir
        if not trash_dir or project_id != self.project_id:
            return False
        original_abs = (self.project_root / file_path).resolve()
        row = self.files_by_abs_path.get(str(original_abs))
        if not row:
            return False
        if not original_abs.exists():
            row["deleted"] = 1
            row["original_path"] = str(original_abs)
            return True
        rel = original_abs.relative_to(self.project_root)
        target = Path(trash_dir) / project_id / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(original_abs), str(target))
        row["deleted"] = 1
        row["original_path"] = str(original_abs)
        row["version_dir"] = str(Path(trash_dir) / project_id)
        row["path"] = str(target)
        self.files_by_abs_path.pop(str(original_abs), None)
        self.files_by_abs_path[str(target)] = row
        self.deleted_rows.append(dict(row))
        return True

    def get_deleted_files(self, project_id: str) -> list[Dict[str, Any]]:
        """Return get deleted files."""
        if project_id != self.project_id:
            return []
        return [r for r in self.deleted_rows if r.get("deleted") == 1]


@pytest.mark.asyncio
async def test_delete_file_db_missing_fs_exists(tmp_path: Path) -> None:
    """Verify test delete file db missing fs exists."""
    project_id = str(uuid.uuid4())
    project_root = tmp_path / "project"
    trash_root = tmp_path / "trash"
    project_root.mkdir()
    file_rel = "notes/fallback_delete.txt"
    file_abs = project_root / file_rel
    file_abs.parent.mkdir(parents=True)
    file_abs.write_text("one\ntwo\nthree\n", encoding="utf-8")

    db = _FakeDB(project_id, project_root, trash_root)
    cmd = MarkFileDeletedCommand(
        database=cast(Any, db),
        project_id=project_id,
        file_path=file_rel,
        trash_dir=str(trash_root),
    )
    result = await cmd.execute()

    assert result["success"] is True
    assert result["db_lookup_found"] is False
    assert result["fs_fallback_used"] is True
    assert result["file_existed_on_disk"] is True
    assert result["db_row_created"] is True
    assert result["deleted"] is True
    assert result["moved_to_trash"] is True
    assert not file_abs.exists()
    deleted_rows = db.get_deleted_files(project_id)
    assert len(deleted_rows) == 1
    assert deleted_rows[0]["original_path"] == str(file_abs.resolve())


@pytest.mark.asyncio
async def test_delete_file_db_missing_fs_missing(tmp_path: Path) -> None:
    """Verify test delete file db missing fs missing."""
    project_id = str(uuid.uuid4())
    project_root = tmp_path / "project"
    trash_root = tmp_path / "trash"
    project_root.mkdir()
    db = _FakeDB(project_id, project_root, trash_root)

    cmd = MarkFileDeletedCommand(
        database=cast(Any, db),
        project_id=project_id,
        file_path="notes/missing.txt",
        trash_dir=str(trash_root),
    )
    result = await cmd.execute()

    assert result["success"] is False
    assert result["error"] == "FILE_NOT_FOUND"
    assert result["db_lookup_found"] is False
    assert result["fs_fallback_used"] is True
    assert result["file_existed_on_disk"] is False
    assert result["db_row_created"] is False


@pytest.mark.asyncio
async def test_delete_file_db_existing(tmp_path: Path) -> None:
    """Verify test delete file db existing."""
    project_id = str(uuid.uuid4())
    project_root = tmp_path / "project"
    trash_root = tmp_path / "trash"
    project_root.mkdir()
    file_rel = "notes/existing.txt"
    file_abs = project_root / file_rel
    file_abs.parent.mkdir(parents=True)
    file_abs.write_text("abc\n", encoding="utf-8")
    db = _FakeDB(project_id, project_root, trash_root)
    db.add_file(
        path=str(file_abs.resolve()),
        lines=1,
        last_modified=file_abs.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )

    cmd = MarkFileDeletedCommand(
        database=cast(Any, db),
        project_id=project_id,
        file_path=file_rel,
        trash_dir=str(trash_root),
    )
    result = await cmd.execute()

    assert result["success"] is True
    assert result["db_lookup_found"] is True
    assert result["fs_fallback_used"] is False
    assert result["db_row_created"] is False


@pytest.mark.asyncio
async def test_delete_file_rejects_path_traversal(tmp_path: Path) -> None:
    """Verify test delete file rejects path traversal."""
    project_id = str(uuid.uuid4())
    project_root = tmp_path / "project"
    trash_root = tmp_path / "trash"
    project_root.mkdir()
    db = _FakeDB(project_id, project_root, trash_root)

    cmd = MarkFileDeletedCommand(
        database=cast(Any, db),
        project_id=project_id,
        file_path="../outside.txt",
        trash_dir=str(trash_root),
    )
    result = await cmd.execute()

    assert result["success"] is False
    assert result["error"] == "INVALID_FILE_PATH"


@pytest.mark.asyncio
async def test_delete_file_rejects_absolute_path(tmp_path: Path) -> None:
    """Verify test delete file rejects absolute path."""
    project_id = str(uuid.uuid4())
    project_root = tmp_path / "project"
    trash_root = tmp_path / "trash"
    project_root.mkdir()
    db = _FakeDB(project_id, project_root, trash_root)

    cmd = MarkFileDeletedCommand(
        database=cast(Any, db),
        project_id=project_id,
        file_path="/tmp/file.txt",
        trash_dir=str(trash_root),
    )
    result = await cmd.execute()

    assert result["success"] is False
    assert result["error"] == "INVALID_FILE_PATH"


@pytest.mark.asyncio
async def test_delete_file_postgres_like_driver_without_db_path(tmp_path: Path) -> None:
    """Verify test delete file postgres like driver without db path."""
    project_id = str(uuid.uuid4())
    project_root = tmp_path / "project"
    trash_root = tmp_path / "trash"
    project_root.mkdir()
    file_rel = "notes/pg_like.txt"
    file_abs = project_root / file_rel
    file_abs.parent.mkdir(parents=True)
    file_abs.write_text("hello\n", encoding="utf-8")

    db = _FakeDB(project_id, project_root, trash_root)
    assert not hasattr(db, "db_path")
    cmd = MarkFileDeletedCommand(
        database=cast(Any, db),
        project_id=project_id,
        file_path=file_rel,
        trash_dir=str(trash_root),
    )
    result = await cmd.execute()

    assert result["success"] is True
    assert result["fs_fallback_used"] is True
