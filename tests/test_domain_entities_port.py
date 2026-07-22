"""
Driver-direct ``domain/entities.py`` parity with ``_ClientAPIClassesFunctionsMixin``/
``_ClientAPIMethodsImportsMixin``/``_ClientAPIIssuesUsagesMixin`` (stage 2 layer
collapse, Block B, Part 1).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analysis.core.database_driver_pkg.domain import entities as domain_entities
from code_analysis.core.database_client.objects.analysis import Issue


class _FakeDriver:
    """Minimal driver stub for entities port tests."""

    def __init__(
        self,
        execute_rows: Optional[List[Dict[str, Any]]] = None,
        select_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Store canned execute/select responses."""
        self._execute_rows = execute_rows if execute_rows is not None else []
        self._select_rows = select_rows if select_rows is not None else []
        self.execute_calls: List[Any] = []
        self.select_calls: List[Any] = []
        self.insert_calls: List[Any] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Record and return canned rows."""
        self.execute_calls.append((sql, params))
        return {"data": self._execute_rows}

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Record and return canned rows."""
        self.select_calls.append((table_name, where, order_by))
        return self._select_rows

    def insert(self, table_name: str, data: Dict[str, Any]) -> Any:
        """Record an insert, return a fake row id."""
        self.insert_calls.append((table_name, data))
        return 9


def test_search_classes_with_project_id_joins_files() -> None:
    """project_id given -> JOIN files query, name LIKE clause appended when provided."""
    driver = _FakeDriver(execute_rows=[{"id": 1, "file_id": 1, "name": "Foo", "line": 3}])

    result = domain_entities.search_classes(driver, project_id="proj-1", name="Fo")

    assert len(result) == 1
    sql, params = driver.execute_calls[0]
    assert "JOIN files" in sql
    assert "name LIKE" in sql
    assert params == ("proj-1", "%Fo%")


def test_search_classes_no_project_id_uses_select() -> None:
    """No project_id, no name -> plain select(), no execute()."""
    driver = _FakeDriver(select_rows=[{"id": 1, "file_id": 1, "name": "Foo", "line": 1}])

    result = domain_entities.search_classes(driver)

    assert len(result) == 1
    assert driver.execute_calls == []
    table, where, order_by = driver.select_calls[0]
    assert table == "classes"
    assert order_by == ["line"]


def test_get_class_methods_scoped_by_class_id() -> None:
    """get_class_methods: select scoped to class_id, ordered by line."""
    driver = _FakeDriver(
        select_rows=[{"id": 1, "class_id": 5, "name": "m", "line": 2}]
    )

    result = domain_entities.get_class_methods(driver, 5)

    assert len(result) == 1
    table, where, order_by = driver.select_calls[0]
    assert where == {"class_id": 5}


def test_search_methods_with_name_builds_like_sql() -> None:
    """search_methods: name given -> LIKE SQL via execute(), class_id/is_abstract optional."""
    driver = _FakeDriver(execute_rows=[{"id": 1, "class_id": 5, "name": "m", "line": 2}])

    result = domain_entities.search_methods(driver, class_id=5, name="m", is_abstract=True)

    assert len(result) == 1
    sql, params = driver.execute_calls[0]
    assert "class_id = ?" in sql
    assert "is_abstract = ?" in sql
    assert params == (5, "%m%", True)


def test_create_issue_inserts_then_refetches() -> None:
    """create_issue: insert() then select({"id": row_id}) to hydrate the Issue."""
    issue = Issue(id=None, project_id="proj-1", file_id=1, issue_type="cycle", description="x")
    driver = _FakeDriver(select_rows=[{"id": 9, "project_id": "proj-1", "issue_type": "cycle"}])

    result = domain_entities.create_issue(driver, issue)

    assert isinstance(result, Issue)
    assert result.id == 9
    assert len(driver.insert_calls) == 1
