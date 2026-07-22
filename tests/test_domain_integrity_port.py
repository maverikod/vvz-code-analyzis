"""
Driver-direct ``domain/integrity.py`` parity with ``_ClientAPIIntegrityMixin``
(stage 2 layer collapse, Block B, Part 1).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analysis.core.database_driver_pkg.domain import integrity as domain_integrity


class _TxDriver:
    """Fake recording begin/execute_batch/commit/rollback for the cycle-detection batch."""

    def __init__(self, batch_results: List[Dict[str, Any]]) -> None:
        """Store the canned per-op results returned by execute_batch."""
        self._batch_results = batch_results
        self.calls: List[str] = []
        self.raise_on_batch: Optional[Exception] = None

    def begin_transaction(self) -> str:
        """Record begin, return a fake tid."""
        self.calls.append("begin")
        return "tid-1"

    def execute_batch(self, operations: Any, transaction_id: str) -> List[Dict[str, Any]]:
        """Record execute_batch; optionally raise to exercise the rollback path."""
        self.calls.append("execute_batch")
        assert transaction_id == "tid-1"
        if self.raise_on_batch is not None:
            raise self.raise_on_batch
        return self._batch_results

    def commit_transaction(self, tid: str) -> bool:
        """Record commit."""
        self.calls.append("commit")
        assert tid == "tid-1"
        return True

    def rollback_transaction(self, tid: str) -> bool:
        """Record rollback."""
        self.calls.append("rollback")
        assert tid == "tid-1"
        return True


def test_fetch_import_cycle_paths_commits_and_parses_last_batch_result() -> None:
    """Happy path: begin/execute_batch/commit, cycles parsed from the last op's rows."""
    driver = _TxDriver(
        [
            {"affected_rows": 0},
            {"affected_rows": 0},
            {"data": [{"chain": "a.py,b.py,a.py"}]},
        ]
    )

    result = domain_integrity.fetch_import_cycle_paths(driver, "proj-1")

    assert driver.calls == ["begin", "execute_batch", "commit"]
    assert isinstance(result, list)


def test_fetch_import_cycle_paths_no_results_returns_empty() -> None:
    """execute_batch returning falsy -> empty list, no crash."""
    driver = _TxDriver([])

    result = domain_integrity.fetch_import_cycle_paths(driver, "proj-1")

    assert result == []


def test_fetch_import_cycle_paths_rolls_back_and_reraises_on_failure() -> None:
    """A failure mid-batch rolls back the transaction and re-raises."""
    driver = _TxDriver([])
    driver.raise_on_batch = RuntimeError("boom")

    try:
        domain_integrity.fetch_import_cycle_paths(driver, "proj-1")
        assert False, "expected RuntimeError to propagate"
    except RuntimeError:
        pass

    assert driver.calls == ["begin", "execute_batch", "rollback"]


class _DeleteDriver:
    """Fake recording the DELETE issued by clear_project_integrity_issues."""

    def __init__(self, affected_rows: int) -> None:
        """Store the canned affected_rows."""
        self._affected_rows = affected_rows
        self.calls: List[Any] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Record and answer the DELETE."""
        self.calls.append((sql, params))
        return {"affected_rows": self._affected_rows}


def test_clear_project_integrity_issues_empty_types_is_noop() -> None:
    """Empty issue_types -> 0, no execute() call at all."""
    driver = _DeleteDriver(5)

    result = domain_integrity.clear_project_integrity_issues(driver, "proj-1", [])

    assert result == 0
    assert driver.calls == []


def test_clear_project_integrity_issues_returns_affected_rows() -> None:
    """Non-empty issue_types -> DELETE issued, affected_rows returned as int."""
    driver = _DeleteDriver(3)

    result = domain_integrity.clear_project_integrity_issues(
        driver, "proj-1", ["cycle", "unused_import"]
    )

    assert result == 3
    sql, params = driver.calls[0]
    assert "DELETE FROM issues" in sql
    assert params == ("proj-1", "cycle", "unused_import")
