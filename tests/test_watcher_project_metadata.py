"""
Tests for watcher project metadata sync and updated_at accumulation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analysis.core.file_watcher_pkg.watcher_project_metadata import (
    apply_project_updated_at_from_scan,
    max_unix_mtime_from_project_files,
    refresh_project_metadata_from_projectid,
)
from code_analysis.core.project_resolution import (
    load_project_info,
    update_projectid_fields,
)
from code_analysis.core.sql_portable import unix_timestamp_to_julian_day


def _write_projectid(root: Path, **fields: object) -> None:
    """Return write projectid."""
    payload = {
        "id": fields.get("id", "550e8400-e29b-41d4-a716-446655440000"),
        "description": fields.get("description", "test project"),
    }
    if fields.get("deleted"):
        payload["deleted"] = True
    if fields.get("processing_paused"):
        payload["processing_paused"] = True
    (root / "projectid").write_text(
        json.dumps(payload, indent=4) + "\n",
        encoding="utf-8",
    )


class _FakeDatabase:
    """Represent FakeDatabase."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple, **kwargs: object) -> None:
        """Execute the command."""
        self.calls.append((sql.strip(), params))

    def sync_project_metadata_from_projectid(
        self, root_dir: Path, **kwargs: object
    ) -> str:
        """Return sync project metadata from projectid."""
        info = load_project_info(root_dir)
        self.execute(
            "UPDATE projects SET deleted = ?, processing_paused = ?, comment = ? WHERE id = ?",
            (
                bool(info.deleted),
                bool(info.processing_paused),
                info.description or None,
                info.project_id,
            ),
        )
        return info.project_id


def test_load_project_info_optional_flags_default_false(tmp_path: Path) -> None:
    """Verify test load project info optional flags default false."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_projectid(root)
    info = load_project_info(root)
    assert info.deleted is False
    assert info.processing_paused is False


def test_update_projectid_fields_persists_flags(tmp_path: Path) -> None:
    """Verify test update projectid fields persists flags."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_projectid(root)
    update_projectid_fields(root, deleted=True, processing_paused=True, backup=False)
    info = load_project_info(root)
    assert info.deleted is True
    assert info.processing_paused is True


def test_max_unix_mtime_from_project_files() -> None:
    """Verify test max unix mtime from project files."""
    files = {
        "a": {"mtime": 100.0},
        "b": {"mtime": 250.5},
        "c": {"mtime": 200.0},
    }
    assert max_unix_mtime_from_project_files(files) == 250.5
    assert max_unix_mtime_from_project_files({}) is None


def test_apply_project_updated_at_from_scan_advances_only_when_newer() -> None:
    """Verify test apply project updated at from scan advances only when newer."""
    db = _FakeDatabase()
    mtime = 1_700_000_000.0
    jd = unix_timestamp_to_julian_day(mtime)
    apply_project_updated_at_from_scan(
        db,
        "550e8400-e29b-41d4-a716-446655440000",
        {"f.py": {"mtime": mtime}},
    )
    assert len(db.calls) == 1
    _sql, params = db.calls[0]
    assert params[0] == pytest.approx(jd)
    assert params[1] == "550e8400-e29b-41d4-a716-446655440000"
    assert params[2] == pytest.approx(jd)


def test_refresh_project_metadata_from_projectid(tmp_path: Path) -> None:
    """Verify test refresh project metadata from projectid."""
    root = tmp_path / "proj"
    root.mkdir()
    _write_projectid(root, processing_paused=True)
    db = _FakeDatabase()
    pid = refresh_project_metadata_from_projectid(db, root)
    assert pid == "550e8400-e29b-41d4-a716-446655440000"
    assert db.calls[0][1][1] is True
