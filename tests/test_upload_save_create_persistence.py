"""
T5: create-mode upload-save must not return a phantom (non-persisted) file_id.

``ProjectFileTransferUploadSaveCommand`` registers a ``files`` row before writing
bytes and returns its id. The durability post-condition re-reads the row on a
fresh statement and only returns the id when the row is actually visible; a
non-persisted row is rolled back and surfaced as ``FILE_REGISTER_NOT_PERSISTED``.
These unit tests exercise that gate (`_create_row_is_persisted`) directly.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from code_analysis.commands.project_file_transfer_by_id_commands import (
    _create_row_is_persisted,
)


class _FakeDB:
    """Database stub exposing only get_file_by_path with a canned row."""

    def __init__(self, row: Optional[Dict[str, Any]]) -> None:
        self._row = row
        self.calls: list[tuple] = []

    def get_file_by_path(
        self, path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        self.calls.append((path, project_id, include_deleted))
        return self._row


def test_persisted_true_when_row_id_matches(tmp_path: Path) -> None:
    db = _FakeDB({"id": "fid-1"})
    assert _create_row_is_persisted(db, "p1", tmp_path / "f.yaml", "fid-1") is True
    # It re-reads through the database (fresh visibility check).
    assert db.calls and db.calls[0][1] == "p1"


def test_persisted_false_when_row_missing(tmp_path: Path) -> None:
    db = _FakeDB(None)
    assert _create_row_is_persisted(db, "p1", tmp_path / "f.yaml", "fid-1") is False


def test_persisted_false_on_id_mismatch(tmp_path: Path) -> None:
    db = _FakeDB({"id": "some-other-id"})
    assert _create_row_is_persisted(db, "p1", tmp_path / "f.yaml", "fid-1") is False


def test_persisted_true_when_client_cannot_answer(tmp_path: Path) -> None:
    class _NoLookup:
        pass

    assert (
        _create_row_is_persisted(_NoLookup(), "p1", tmp_path / "f.yaml", "fid-1")
        is True
    )


def test_persisted_false_when_lookup_raises(tmp_path: Path) -> None:
    class _Boom:
        def get_file_by_path(self, *a: Any, **k: Any) -> Dict[str, Any]:
            raise RuntimeError("db unavailable")

    assert _create_row_is_persisted(_Boom(), "p1", tmp_path / "f.yaml", "fid-1") is False
