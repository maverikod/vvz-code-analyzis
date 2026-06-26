"""
Tests for last_modified handling: update_indexes analyzer and File DB row mapping.

Covers NULL last_modified in DB rows and Unix float passed into File (server write paths).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from code_analysis.commands.update_indexes_analyzer import analyze_file
from code_analysis.core.database_client.objects.file import File


def test_analyze_file_skipped_when_db_mtime_matches_disk() -> None:
    """No read/parse/sync when files.last_modified matches st_mtime within tolerance."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "same.py"
        path.write_text("x = 1\n", encoding="utf-8")
        mtime = path.stat().st_mtime

        class _Db:
            """Represent Db."""

            def get_file_by_path(self, p: str, pid: str):
                """Return get file by path."""
                return {"id": 7, "last_modified": mtime}

            def add_file(self, *a, **k):
                """Return add file."""
                raise AssertionError("add_file must not run when skipped")

        db = _Db()
        with patch(
            "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic"
        ) as sync_mock:
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )
        assert out.get("status") == "skipped"
        assert out.get("reason") == "mtime_unchanged"
        sync_mock.assert_not_called()


def test_analyze_file_succeeds_when_db_last_modified_is_none() -> None:
    """update_indexes must not subtract None from disk mtime."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "m.py"
        code = "def f():\n    return 1\n"
        path.write_text(code, encoding="utf-8")

        class _Db:
            """Represent Db."""

            def get_file_by_path(self, p: str, pid: str):
                """Return get file by path."""
                return {"id": 42, "last_modified": None}

            def add_file(self, *a, **k):
                """Return add file."""
                return 42

            def add_usage(self, *a, **k):
                """Return add usage."""
                return None

            def replace_usages_for_file(self, *a, **k):
                """Return replace usages for file."""
                return 0

            def mark_file_needs_chunking(self, *a, **k):
                """Return mark file needs chunking."""
                return None

        db = _Db()
        with patch(
            "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic"
        ) as sync_mock:
            sync_mock.return_value = {"success": True, "entities_updated": 0}
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )
        assert out.get("status") == "success"
        sync_mock.assert_called_once()


def test_file_to_db_row_preserves_unix_float_last_modified() -> None:
    """Server flows pass Unix mtime as float; DB row must store a REAL, not NULL."""
    ts = 1_700_000_000.25
    f = File(
        project_id="proj",
        path="/tmp/x.py",
        lines=1,
        last_modified=ts,
        has_docstring=False,
    )
    row = f.to_db_row()
    assert row["last_modified"] == ts


def test_file_to_db_row_datetime_still_julian_encodes() -> None:
    """Verify test file to db row datetime still julian encodes."""
    from datetime import datetime

    dt = datetime(2024, 1, 15, 12, 0, 0)
    f = File(
        project_id="proj",
        path="/tmp/y.py",
        lines=1,
        last_modified=dt,
        has_docstring=True,
    )
    row = f.to_db_row()
    assert row["last_modified"] is not None
    assert isinstance(row["last_modified"], float)
