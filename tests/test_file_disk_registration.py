"""
Tests for file_disk_registration.ensure_file_row_for_disk_path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from code_analysis.core.file_disk_registration import (
    collect_file_disk_metadata,
    ensure_file_row_for_disk_path,
)


class _FakeDatabase:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.chunking: List[str] = []

    def get_project(self, project_id: str) -> Any:
        if project_id == "project-1":
            return SimpleNamespace(root_path=str(self.root), watch_dir_id="wd-1")
        return None

    def get_file_by_path(
        self, path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        rel = str(Path(path).resolve().relative_to(self.root))
        row = self.rows.get(rel)
        if row and row.get("deleted") and not include_deleted:
            return None
        return row

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> str:
        rel = str(Path(path).resolve().relative_to(self.root))
        file_id = f"id:{rel}"
        self.rows[rel] = {
            "id": file_id,
            "project_id": project_id,
            "relative_path": rel,
            "lines": lines,
            "last_modified": last_modified,
            "has_docstring": has_docstring,
            "deleted": False,
        }
        return file_id

    def execute(self, sql: str, params: Any = None) -> Dict[str, Any]:
        text = " ".join(sql.split()).lower()
        params = tuple(params or ())
        if "update files set needs_chunking = 1 where id" in text:
            self.chunking.append(str(params[0]))
            return {"affected_rows": 1}
        return {"affected_rows": 0}


def test_collect_file_disk_metadata_python_file(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text('"""doc"""\nx = 1\n', encoding="utf-8")
    lines, has_doc = collect_file_disk_metadata(target)
    assert lines == 3
    assert has_doc is True


def test_ensure_file_row_registers_missing_file(tmp_path: Path) -> None:
    target = tmp_path / "src" / "new.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('hi')\n", encoding="utf-8")
    db = _FakeDatabase(tmp_path)
    row = ensure_file_row_for_disk_path(db, "project-1", target)
    assert row is not None
    assert row["id"] == "id:src/new.py"
    assert db.get_file_by_path(str(target), "project-1") is not None


def test_ensure_file_row_idempotent_and_marks_chunking(tmp_path: Path) -> None:
    target = tmp_path / "b.py"
    target.write_text("x = 1\n", encoding="utf-8")
    db = _FakeDatabase(tmp_path)
    first = ensure_file_row_for_disk_path(
        db, "project-1", target, mark_needs_chunking=True
    )
    second = ensure_file_row_for_disk_path(
        db, "project-1", target, mark_needs_chunking=True
    )
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    assert db.chunking == ["id:b.py", "id:b.py"]


def test_ensure_file_row_returns_none_for_missing_path(tmp_path: Path) -> None:
    db = _FakeDatabase(tmp_path)
    assert ensure_file_row_for_disk_path(db, "project-1", tmp_path / "nope.py") is None
