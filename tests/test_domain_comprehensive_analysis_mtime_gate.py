"""
Driver-direct ``domain/comprehensive_analysis.py`` parity with
``_ClientAPIComprehensiveAnalysisMixin.should_analyze_file`` (stage 2 layer collapse,
Block B, Part 1). Ports tests/test_comprehensive_analysis_mtime_gate.py's assertions
onto the new free-function form (kept unchanged, still passing, testing the old
mixin).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from code_analysis.core.database_driver_pkg.domain import (
    comprehensive_analysis as domain_ca,
)


class _FakeDriver:
    """Minimal driver stub returning controlled ``execute()`` data."""

    def __init__(self, execute_returns: Dict[str, Any]) -> None:
        """Store the canned execute() response."""
        self._execute_returns = execute_returns

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the canned response regardless of SQL/params."""
        return self._execute_returns


def test_should_analyze_file_no_record() -> None:
    """No DB record -> should_analyze True, reason no_record."""
    driver = _FakeDriver({"data": []})
    out = domain_ca.should_analyze_file(driver, file_id=1, file_mtime=1000.0)
    assert out["should_analyze"] is True
    assert out["reason"] == "no_record"
    assert out["db_mtime"] is None
    assert out["disk_mtime"] == 1000.0


def test_should_analyze_file_disk_newer() -> None:
    """disk_mtime > db_mtime + tolerance -> should_analyze True, reason disk_newer."""
    driver = _FakeDriver({"data": [{"file_mtime": 1000.0}]})
    out = domain_ca.should_analyze_file(driver, file_id=1, file_mtime=1000.2, tolerance=0.1)
    assert out["should_analyze"] is True
    assert out["reason"] == "disk_newer"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 1000.2


def test_should_analyze_file_equal_within_tolerance() -> None:
    """abs(disk_mtime - db_mtime) <= tolerance -> skip, reason equal_within_tolerance."""
    driver = _FakeDriver({"data": [{"file_mtime": 1000.0}]})
    out = domain_ca.should_analyze_file(driver, file_id=1, file_mtime=1000.05, tolerance=0.1)
    assert out["should_analyze"] is False
    assert out["reason"] == "equal_within_tolerance"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 1000.05


def test_should_analyze_file_disk_older() -> None:
    """disk_mtime + tolerance < db_mtime -> skip, reason disk_older."""
    driver = _FakeDriver({"data": [{"file_mtime": 1000.0}]})
    out = domain_ca.should_analyze_file(driver, file_id=1, file_mtime=999.8, tolerance=0.1)
    assert out["should_analyze"] is False
    assert out["reason"] == "disk_older"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 999.8


def test_should_analyze_file_just_above_tolerance_is_newer() -> None:
    """disk_mtime > db_mtime + tolerance -> analyze, reason disk_newer."""
    driver = _FakeDriver({"data": [{"file_mtime": 1000.0}]})
    out = domain_ca.should_analyze_file(driver, file_id=1, file_mtime=1000.11, tolerance=0.1)
    assert out["should_analyze"] is True
    assert out["reason"] == "disk_newer"


def test_should_analyze_file_exactly_at_tolerance_boundary_skip() -> None:
    """disk_mtime within tolerance of db_mtime -> skip (equal_within_tolerance)."""
    driver = _FakeDriver({"data": [{"file_mtime": 1000.0}]})
    out = domain_ca.should_analyze_file(driver, file_id=1, file_mtime=1000.05, tolerance=0.1)
    assert out["should_analyze"] is False
    assert out["reason"] == "equal_within_tolerance"
    assert out["db_mtime"] == 1000.0
    assert out["disk_mtime"] == 1000.05


def test_save_and_get_round_trip_shape() -> None:
    """save_comprehensive_analysis_results -> lastrowid int; get -> results/summary/mtime/date."""

    class _SaveThenGetDriver:
        """Fake capturing an INSERT then answering the follow-up SELECT."""

        def __init__(self) -> None:
            self.saved: Optional[tuple] = None

        def execute(
            self,
            sql: str,
            params: Optional[tuple] = None,
            transaction_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Route INSERT vs SELECT."""
            if "INSERT" in sql:
                self.saved = params
                return {"lastrowid": 7}
            assert self.saved is not None
            file_id, project_id, file_mtime, results_json, summary_json = self.saved
            return {
                "data": [
                    {
                        "results_json": results_json,
                        "summary_json": summary_json,
                        "file_mtime": file_mtime,
                        "updated_at": "2026-07-22T00:00:00",
                    }
                ]
            }

    driver = _SaveThenGetDriver()
    rowid = domain_ca.save_comprehensive_analysis_results(
        driver, 1, "proj-1", 1234.5, {"a": 1}, {"b": 2}
    )
    assert rowid == 7

    fetched = domain_ca.get_comprehensive_analysis_results(driver, 1)
    assert fetched == {
        "results": {"a": 1},
        "summary": {"b": 2},
        "file_mtime": 1234.5,
        "analysis_date": "2026-07-22T00:00:00",
    }


def test_save_batch_empty_items_noop() -> None:
    """Empty items list -> no transaction started at all."""

    class _NoCallDriver:
        """Fails the test if any method is invoked."""

        def begin_transaction(self) -> str:
            """Fail unconditionally: batch save must short-circuit before calling this."""
            raise AssertionError("begin_transaction should not be called for empty items")

    domain_ca.save_comprehensive_analysis_results_batch(_NoCallDriver(), [])


def test_save_batch_commits_within_one_transaction() -> None:
    """Non-empty items -> begin/execute_batch/commit sequence, no rollback."""

    class _TxDriver:
        """Records the begin/execute_batch/commit/rollback sequence."""

        def __init__(self) -> None:
            self.calls: list[str] = []

        def begin_transaction(self) -> str:
            """Return a fake tid."""
            self.calls.append("begin")
            return "tid-1"

        def execute_batch(self, operations: Any, transaction_id: str) -> Any:
            """Record the batch call."""
            self.calls.append("execute_batch")
            assert transaction_id == "tid-1"
            return [{"affected_rows": 1} for _ in operations]

        def commit_transaction(self, tid: str) -> bool:
            """Record the commit."""
            self.calls.append("commit")
            assert tid == "tid-1"
            return True

        def rollback_transaction(self, tid: str) -> bool:
            """Record the rollback (should not be reached)."""
            self.calls.append("rollback")
            return True

    driver = _TxDriver()
    domain_ca.save_comprehensive_analysis_results_batch(
        driver, [(1, "proj-1", 1000.0, {"a": 1}, {"b": 2})]
    )
    assert driver.calls == ["begin", "execute_batch", "commit"]
