"""
Unit tests for the whole-project exclusive lock helper module (bugs 88f06abc,
5da73265).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from code_analysis.core.project_exclusive_lock import (
    acquire_project_exclusive_lock,
    emergency_unlock_project_lock,
    get_project_exclusive_lock,
    is_project_exclusively_locked,
    release_project_exclusive_lock,
)

_PID = "550e8400-e29b-41d4-a716-446655440000"


class _FakeLockDriver:
    """Minimal duck-typed driver double: ``.select()`` / ``.execute()`` only.

    Models on ``tests/test_base_mcp_command_validate_project.py``'s
    ``_ScopedMissGlobalHitDb``-style doubles: a real single-row table backing
    store, not a mocked return value.
    """

    def __init__(self) -> None:
        """Initialize the instance with an empty lock-row store."""
        self._rows: Dict[str, Dict[str, Any]] = {}

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the lock row for ``where["project_id"]`` if present."""
        assert table_name == "project_exclusive_locks"
        pid = str((where or {}).get("project_id") or "")
        row = self._rows.get(pid)
        return [dict(row)] if row else []

    def execute(
        self, sql: str, params: Optional[tuple] = None, transaction_id: Any = None
    ) -> Dict[str, Any]:
        """Emulate the two SQL statements the module issues."""
        if sql.startswith("INSERT INTO project_exclusive_locks"):
            project_id, locked_at, owner, reason = params  # type: ignore[misc]
            if project_id in self._rows:
                return {"affected_rows": 0}
            self._rows[project_id] = {
                "project_id": project_id,
                "locked_at": locked_at,
                "owner": owner,
                "reason": reason,
            }
            return {"affected_rows": 1}
        if sql.startswith("DELETE FROM project_exclusive_locks"):
            (project_id,) = params  # type: ignore[misc]
            existed = project_id in self._rows
            self._rows.pop(project_id, None)
            return {"affected_rows": 1 if existed else 0}
        raise AssertionError(f"unexpected SQL: {sql}")


def test_acquire_sets_row_and_returns_true() -> None:
    """First acquire on an unlocked project inserts a row and returns True."""
    db = _FakeLockDriver()

    ok = acquire_project_exclusive_lock(db, _PID, owner="tester", reason="unit test")

    assert ok is True
    row = get_project_exclusive_lock(db, _PID)
    assert row is not None
    assert row["owner"] == "tester"
    assert row["reason"] == "unit test"


def test_acquire_twice_returns_false_and_does_not_change_row() -> None:
    """Acquiring an already-held lock returns False without mutating the row."""
    db = _FakeLockDriver()
    acquire_project_exclusive_lock(db, _PID, owner="first", reason="r1")

    ok = acquire_project_exclusive_lock(db, _PID, owner="second", reason="r2")

    assert ok is False
    row = get_project_exclusive_lock(db, _PID)
    assert row is not None
    assert row["owner"] == "first"
    assert row["reason"] == "r1"


def test_is_locked_reflects_state_across_acquire_release() -> None:
    """is_project_exclusively_locked flips True after acquire, False after release."""
    db = _FakeLockDriver()

    assert is_project_exclusively_locked(db, _PID) is False

    acquire_project_exclusive_lock(db, _PID, owner="tester", reason="r")
    assert is_project_exclusively_locked(db, _PID) is True

    release_project_exclusive_lock(db, _PID)
    assert is_project_exclusively_locked(db, _PID) is False


def test_release_is_idempotent_noop_when_nothing_locked() -> None:
    """Releasing an unlocked project is a silent no-op, not an error."""
    db = _FakeLockDriver()

    release_project_exclusive_lock(db, _PID)  # must not raise

    assert get_project_exclusive_lock(db, _PID) is None


def test_emergency_unlock_requires_force_true() -> None:
    """emergency_unlock_project_lock raises ValueError when force is not True."""
    db = _FakeLockDriver()
    acquire_project_exclusive_lock(db, _PID, owner="tester", reason="r")

    with pytest.raises(ValueError):
        emergency_unlock_project_lock(
            db, _PID, force=False, reason="oops", mismatch=None
        )

    # Lock must remain held: refusal happened before any release.
    assert is_project_exclusively_locked(db, _PID) is True


def test_emergency_unlock_with_force_clears_and_returns_audit_dict() -> None:
    """force=True clears the lock and returns an audit dict with the expected keys."""
    db = _FakeLockDriver()
    acquire_project_exclusive_lock(db, _PID, owner="stuck-owner", reason="mid-rename")

    audit = emergency_unlock_project_lock(
        db, _PID, force=True, reason="stuck rename", mismatch={"note": "disk moved"}
    )

    assert is_project_exclusively_locked(db, _PID) is False
    assert audit["project_id"] == _PID
    assert audit["cleared"] is True
    assert audit["reason"] == "stuck rename"
    assert audit["previous_lock"] is not None
    assert audit["previous_lock"]["owner"] == "stuck-owner"


def test_emergency_unlock_with_force_when_nothing_locked_reports_previous_lock_none() -> None:
    """Clearing a project that was never locked is valid; previous_lock is None."""
    db = _FakeLockDriver()

    audit = emergency_unlock_project_lock(
        db, _PID, force=True, reason="preventive check", mismatch=None
    )

    assert audit["cleared"] is True
    assert audit["previous_lock"] is None
