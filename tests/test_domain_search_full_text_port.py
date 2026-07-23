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


def test_full_text_search_project_scoped_select_carries_project_attribution() -> None:
    """Project-scoped fulltext SELECT still carries project_id/project_name (attribution
    in both modes, bug — search(project_id=None) = all projects)."""
    driver = _FakeDriver([])

    domain_search.full_text_search(driver, "foo", "proj-1")

    sql, _params = driver.calls[0]
    assert "f.project_id AS project_id" in sql
    assert "p.name AS project_name" in sql
    assert "INNER JOIN projects p ON p.id = f.project_id" in sql


def test_full_text_search_global_empty_query_returns_empty_without_execute() -> None:
    """Global variant: same empty-query short-circuit as the project-scoped one."""
    driver = _FakeDriver([{"entity_name": "x"}])

    result = domain_search.full_text_search_global(driver, "///")

    assert result == []
    assert driver.calls == []


def test_full_text_search_global_has_no_project_id_filter_and_carries_attribution() -> None:
    """Global variant: no project_id bound param, no WHERE f.project_id filter,
    but project_id/project_name attribution columns ARE in the SELECT."""
    rows = [
        {
            "entity_type": "function",
            "entity_name": "foo",
            "content": "def foo(): pass",
            "docstring": None,
            "file_path": "a.py",
            "project_id": "proj-1",
            "project_name": "proj-one",
        }
    ]
    driver = _FakeDriver(rows)

    result = domain_search.full_text_search_global(driver, "foo bar", limit=5)

    assert result == rows
    sql, params = driver.calls[0]
    assert "WHERE f.project_id" not in sql
    assert "f.project_id AS project_id" in sql
    assert "p.name AS project_name" in sql
    assert "INNER JOIN projects p ON p.id = f.project_id" in sql
    # fts_query, fts_query, limit - no project_id bound anywhere
    assert params == ("foo bar", "foo bar", 5)
    assert "proj-1" not in params


def test_full_text_search_global_entity_type_filter_appended() -> None:
    """Global variant: entity_type filter still appends its own clause/param."""
    driver = _FakeDriver([])

    domain_search.full_text_search_global(driver, "foo", entity_type="class", limit=10)

    sql, params = driver.calls[0]
    assert "c.entity_type = ?" in sql
    assert params == ("foo", "foo", "class", 10)
