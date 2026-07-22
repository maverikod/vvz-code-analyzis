"""
Driver-direct ``domain/files.py`` parity with ``_ClientAPIFilesMixin`` (stage 2 layer
collapse, Block B, Part 1).

Covers the flagged exact-shape risk: ``get_project_file_rows`` (raw, unparsed
``last_modified``, used by the file watcher) must stay behaviorally distinct from
``get_project_files`` (returns ``File`` objects) - conflating them was a historical
bug source.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

from code_analysis.core.database_driver_pkg.domain import files as domain_files
from code_analysis.core.database_client.objects.file import File


class _FakeDriver:
    """Minimal driver stub for the files-domain port tests."""

    def __init__(
        self,
        select_rows: Optional[List[Dict[str, Any]]] = None,
        execute_rows: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store canned select/execute responses."""
        self._select_rows = select_rows if select_rows is not None else []
        self._execute_rows = execute_rows if execute_rows is not None else {}
        self.insert_calls: List[Any] = []
        self.execute_calls: List[Any] = []
        self.select_calls: List[Any] = []

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Record and return the canned select rows."""
        self.select_calls.append((table_name, where, limit, offset, order_by))
        return self._select_rows

    def insert(self, table_name: str, data: Dict[str, Any]) -> Any:
        """Record an insert call."""
        self.insert_calls.append((table_name, data))
        return 1

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Record and return the canned execute response."""
        self.execute_calls.append((sql, params))
        return self._execute_rows


def test_get_project_file_rows_returns_raw_last_modified_unparsed() -> None:
    """get_project_file_rows: raw dicts, last_modified untouched (Unix timestamp)."""
    raw_rows = [
        {"id": "f1", "path": "a.py", "last_modified": 1_700_000_000.123, "deleted": 0}
    ]
    driver = _FakeDriver(select_rows=raw_rows)

    result = domain_files.get_project_file_rows(driver, "proj-1")

    assert result == raw_rows
    assert result[0]["last_modified"] == 1_700_000_000.123  # untouched, not Julian
    table, where, _limit, _offset, order_by = driver.select_calls[0]
    assert table == "files"
    assert where == {"project_id": "proj-1", "deleted": 0}
    assert order_by == ["path"]


def test_get_project_file_rows_include_deleted_omits_deleted_filter() -> None:
    """include_deleted=True -> where clause has no `deleted` key."""
    driver = _FakeDriver(select_rows=[])

    domain_files.get_project_file_rows(driver, "proj-1", include_deleted=True)

    _table, where, _limit, _offset, _order_by = driver.select_calls[0]
    assert "deleted" not in where


def test_get_project_files_returns_file_objects_not_raw_dicts() -> None:
    """get_project_files: File dataclass objects (distinct from get_project_file_rows' dicts)."""
    raw_rows = [{"id": 1, "project_id": "proj-1", "path": "a.py"}]
    driver = _FakeDriver(select_rows=raw_rows)

    result = domain_files.get_project_files(driver, "proj-1")

    assert len(result) == 1
    assert isinstance(result[0], File)
    assert result[0].path == "a.py"


def test_create_file_inserts_then_refetches() -> None:
    """create_file: insert() then select() to hydrate the returned File."""
    f = File(id=None, project_id="proj-1", path="a.py")
    driver = _FakeDriver(
        select_rows=[{"id": 5, "project_id": "proj-1", "path": "a.py"}]
    )

    result = domain_files.create_file(driver, f)

    assert isinstance(result, File)
    assert result.id == 5
    assert len(driver.insert_calls) == 1


def test_create_file_missing_after_insert_raises() -> None:
    """create_file: refetch miss (0 rows) -> ValueError, not a silent None."""
    f = File(id=None, project_id="proj-1", path="a.py")
    driver = _FakeDriver(select_rows=[])

    try:
        domain_files.create_file(driver, f)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Failed to create file" in str(e)


def test_get_file_by_path_returns_none_when_project_missing() -> None:
    """get_file_by_path: project not found -> None (no execute against files)."""
    driver = _FakeDriver()

    with patch(
        "code_analysis.core.database_driver_pkg.domain.files.get_project",
        return_value=None,
    ):
        result = domain_files.get_file_by_path(driver, "/abs/a.py", "proj-1")

    assert result is None
    assert driver.execute_calls == []


def test_mark_file_needs_chunking_deletes_chunks_and_sets_flag() -> None:
    """mark_file_needs_chunking: chunk DELETE + needs_chunking UPDATE, returns True."""
    driver = _FakeDriver(execute_rows={"affected_rows": 1})

    with patch(
        "code_analysis.core.database_driver_pkg.domain.files.get_file_by_path",
        return_value={"id": "f1", "deleted": False},
    ):
        result = domain_files.mark_file_needs_chunking(driver, "/abs/a.py", "proj-1")

    assert result is True
    sqls = [c[0] for c in driver.execute_calls]
    assert any("DELETE FROM code_chunks" in s for s in sqls)
    assert any("needs_chunking = 1" in s for s in sqls)


def test_mark_file_needs_chunking_already_deleted_returns_false() -> None:
    """mark_file_needs_chunking: row already soft-deleted -> False, no execute() calls."""
    driver = _FakeDriver()

    with patch(
        "code_analysis.core.database_driver_pkg.domain.files.get_file_by_path",
        return_value={"id": "f1", "deleted": True},
    ):
        result = domain_files.mark_file_needs_chunking(driver, "/abs/a.py", "proj-1")

    assert result is False
    assert driver.execute_calls == []


def test_mark_file_needs_chunking_no_row_returns_false() -> None:
    """mark_file_needs_chunking: no matching file -> False."""
    driver = _FakeDriver()

    with patch(
        "code_analysis.core.database_driver_pkg.domain.files.get_file_by_path",
        return_value=None,
    ):
        result = domain_files.mark_file_needs_chunking(driver, "/abs/a.py", "proj-1")

    assert result is False
