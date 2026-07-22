"""
Driver-direct ``domain/search.py`` parity with ``_ClientAPISearchMixin.full_text_search``
(stage 2 layer collapse, Block B, Part 1).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from code_analysis.core.database_driver_pkg.domain import search as domain_search


class _FakeDriver:
    """Records the ``execute`` call and returns a canned row set."""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        """Store canned rows."""
        self._rows = rows
        self.calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Record and return the canned rows."""
        self.calls.append((sql, tuple(params or ())))
        return {"data": self._rows}


def test_full_text_search_empty_query_returns_empty_without_execute() -> None:
    """A query with no real tokens (e.g. '///') short-circuits before any execute()."""
    driver = _FakeDriver([{"entity_name": "x"}])

    result = domain_search.full_text_search(driver, "///", "proj-1")

    assert result == []
    assert driver.calls == []


def test_full_text_search_builds_tsvector_query_and_returns_rows() -> None:
    """Real query -> tsvector/plainto_tsquery SQL against code_content, rows returned as-is."""
    rows = [
        {
            "entity_type": "function",
            "entity_name": "foo",
            "content": "def foo(): pass",
            "docstring": None,
            "file_path": "a.py",
        }
    ]
    driver = _FakeDriver(rows)

    result = domain_search.full_text_search(driver, "foo bar", "proj-1", limit=5)

    assert result == rows
    assert len(driver.calls) == 1
    sql, params = driver.calls[0]
    assert "plainto_tsquery" in sql
    assert "to_tsvector" in sql
    assert "code_content" in sql
    # fts_query, project_id, fts_query, limit (no entity_type filter requested)
    assert params == ("foo bar", "proj-1", "foo bar", 5)


def test_full_text_search_entity_type_filter_appended() -> None:
    """entity_type filter appends an extra SQL clause and an extra bound param."""
    driver = _FakeDriver([])

    domain_search.full_text_search(driver, "foo", "proj-1", entity_type="class", limit=10)

    sql, params = driver.calls[0]
    assert "c.entity_type = ?" in sql
    assert params == ("foo", "proj-1", "foo", "class", 10)
