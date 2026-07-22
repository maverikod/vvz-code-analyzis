"""
Unit tests for comprehensive_analysis mtime gate: should_analyze_file logic.

Covers: no record -> analyze; disk newer -> analyze;
equal within tolerance -> skip; disk older -> skip.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from code_analysis.core.database_driver_pkg.domain.comprehensive_analysis import (
    should_analyze_file,
)


class _MockDbForGate:
    """Minimal mock that returns controlled execute() data for gate tests."""

    def __init__(self, execute_returns: Dict[str, Any]) -> None:
        """Initialize the instance."""
        self._execute_returns = execute_returns

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the command."""
        return self._execute_returns


def test_should_analyze_file_no_record() -> None:
    """No DB record -> should_analyze True, reason no_record."""
    db = _MockDbForGate({"data": []})
    out = should_analyze_file(db, file_id=1, file_mtime=1000.0)
    assert out["should_analyze"] is True
    assert out["reason"] == "no_record"
    assert out["db_mtime"] is None
    assert out["disk_mtime"] == 1000.0


def test_should_analyze_file_disk_newer() -> None:
    """disk_mtime > db_mtime + tolerance -> should_analyze True, reason disk_newer."""
    db = _MockDbForGate({"data": [{"file_mtime": 1000.0}]})
    out = should_analyze_file(db, file_id=1, file_mtime=1000.2, tolerance=0.1)
    assert out["should_analyze"] is True
    assert out["reason"] == "disk_newer"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 1000.2


def test_should_analyze_file_equal_within_tolerance() -> None:
    """abs(disk_mtime - db_mtime) <= tolerance -> skip, reason equal_within_tolerance."""
    db = _MockDbForGate({"data": [{"file_mtime": 1000.0}]})
    out = should_analyze_file(db, file_id=1, file_mtime=1000.05, tolerance=0.1)
    assert out["should_analyze"] is False
    assert out["reason"] == "equal_within_tolerance"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 1000.05


def test_should_analyze_file_disk_older() -> None:
    """disk_mtime + tolerance < db_mtime -> skip, reason disk_older."""
    db = _MockDbForGate({"data": [{"file_mtime": 1000.0}]})
    out = should_analyze_file(db, file_id=1, file_mtime=999.8, tolerance=0.1)
    assert out["should_analyze"] is False
    assert out["reason"] == "disk_older"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 999.8


def test_should_analyze_file_just_above_tolerance_is_newer() -> None:
    """disk_mtime > db_mtime + tolerance -> analyze, reason disk_newer."""
    db = _MockDbForGate({"data": [{"file_mtime": 1000.0}]})
    out = should_analyze_file(db, file_id=1, file_mtime=1000.11, tolerance=0.1)
    assert out["should_analyze"] is True
    assert out["reason"] == "disk_newer"


def test_should_analyze_file_exactly_at_tolerance_boundary_skip() -> None:
    """disk_mtime within tolerance of db_mtime -> skip (equal_within_tolerance)."""
    db = _MockDbForGate({"data": [{"file_mtime": 1000.0}]})
    # Use 1000.05 so clearly within 0.1 of 1000.0; avoids float boundary issues
    out = should_analyze_file(db, file_id=1, file_mtime=1000.05, tolerance=0.1)
    assert out["should_analyze"] is False
    assert out["reason"] == "equal_within_tolerance"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 1000.05
