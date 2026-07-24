"""Unit tests for RawFindingBuffer."""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

from code_analysis.core.search_session.raw_finding_buffer import (
    LOCK_FILENAME,
    RawFindingBuffer,
)


def test_append_finding_serializes_uuid_value(tmp_path) -> None:
    """Bug 29212ab2 regression: real Postgres rows deliver ``project_id`` as an
    actual ``uuid.UUID`` object (not str). ``append_finding``'s ``json.dump``
    must not crash the whole search job on a stray non-JSON-native value -
    it degrades such values to their str() form instead. Prior to the fix
    this raised ``TypeError: Object of type UUID is not JSON serializable``.
    """
    buffer = RawFindingBuffer(tmp_path / "buffer")
    project_id = uuid.uuid4()
    payload = {"result_id": "fulltext-000001", "project_id": project_id}

    written = buffer.append_finding("fulltext-000001", payload)

    assert json.loads(written.read_text(encoding="utf-8")) == {
        "result_id": "fulltext-000001",
        "project_id": str(project_id),
    }


def test_append_list_remove_findings(tmp_path) -> None:
    """Verify test append list remove findings."""
    buffer = RawFindingBuffer(tmp_path / "buffer")
    first = buffer.append_finding("a", {"id": "a"})
    second = buffer.append_finding("b", {"id": "b"})

    listed = buffer.list_findings()
    assert listed == sorted([first, second], key=lambda path: path.stat().st_mtime)
    assert buffer.total_bytes() == first.stat().st_size + second.stat().st_size

    buffer.remove_findings([first])
    assert buffer.list_findings() == [second]
    assert first.exists() is False
    assert json.loads(second.read_text(encoding="utf-8")) == {"id": "b"}


def test_lock_acquire_release(tmp_path) -> None:
    """Verify test lock acquire release."""
    buffer = RawFindingBuffer(tmp_path / "buffer")

    assert buffer.try_acquire_lock() is True
    assert (buffer.buffer_dir / LOCK_FILENAME).read_text(encoding="utf-8") == str(
        os.getpid()
    )

    other = RawFindingBuffer(buffer.buffer_dir)
    assert other.try_acquire_lock() is False

    buffer.release_lock()
    assert other.try_acquire_lock() is True


def test_stale_lock_reclaimed_when_owner_pid_dead(tmp_path) -> None:
    """Verify test stale lock reclaimed when owner pid dead."""
    buffer = RawFindingBuffer(tmp_path / "buffer")
    lock_path = buffer.buffer_dir / LOCK_FILENAME
    lock_path.write_text("999999", encoding="utf-8")

    with patch(
        "code_analysis.core.search_session.raw_finding_buffer.RawFindingBuffer._pid_is_alive",
        return_value=False,
    ):
        assert buffer.try_acquire_lock() is True

    assert lock_path.read_text(encoding="utf-8") == str(os.getpid())
