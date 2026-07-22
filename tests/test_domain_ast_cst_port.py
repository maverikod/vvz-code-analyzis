"""
Driver-direct ``domain/ast_cst.py`` parity with ``_ClientAPIAttributesMixin``
(stage 2 layer collapse, Block B, Part 1).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

from code_analysis.core.database_driver_pkg.domain import ast_cst as domain_ast_cst
from code_analysis.core.database_client.objects.file import File


class _FakeDriver:
    """Minimal driver stub for ast_cst port tests."""

    def __init__(self, select_rows: Optional[List[Dict[str, Any]]] = None) -> None:
        """Store the canned select() response."""
        self._select_rows = select_rows if select_rows is not None else []
        self.insert_calls: List[Any] = []
        self.update_calls: List[Any] = []

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return the canned rows."""
        return self._select_rows

    def insert(self, table_name: str, data: Dict[str, Any]) -> Any:
        """Record an insert."""
        self.insert_calls.append((table_name, data))
        return 1

    def update(self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]) -> int:
        """Record an update."""
        self.update_calls.append((table_name, where, data))
        return 1


def _fake_file(file_id: int = 1) -> File:
    """Return a minimal File for get_file stubbing."""
    return File(id=file_id, project_id="proj-1", path="a.py", last_modified=None)


def test_save_ast_raises_when_file_missing() -> None:
    """save_ast: unknown file_id -> ValueError, no insert/update issued."""
    driver = _FakeDriver()

    with patch(
        "code_analysis.core.database_driver_pkg.domain.ast_cst.get_file",
        return_value=None,
    ):
        try:
            domain_ast_cst.save_ast(driver, 999, {"a": 1})
            assert False, "expected ValueError"
        except ValueError:
            pass

    assert driver.insert_calls == []


def test_save_ast_inserts_when_no_existing_row() -> None:
    """save_ast: no existing (file_id, ast_hash) row -> INSERT."""
    driver = _FakeDriver(select_rows=[])

    with patch(
        "code_analysis.core.database_driver_pkg.domain.ast_cst.get_file",
        return_value=_fake_file(),
    ):
        result = domain_ast_cst.save_ast(driver, 1, {"a": 1})

    assert result is True
    assert len(driver.insert_calls) == 1
    assert driver.insert_calls[0][0] == "ast_trees"


def test_save_ast_updates_when_existing_row() -> None:
    """save_ast: existing (file_id, ast_hash) row -> UPDATE, no INSERT."""
    driver = _FakeDriver(select_rows=[{"id": 42}])

    with patch(
        "code_analysis.core.database_driver_pkg.domain.ast_cst.get_file",
        return_value=_fake_file(),
    ):
        result = domain_ast_cst.save_ast(driver, 1, {"a": 1})

    assert result is True
    assert driver.insert_calls == []
    assert len(driver.update_calls) == 1
    assert driver.update_calls[0][1] == {"id": 42}


def test_get_ast_returns_none_when_no_rows() -> None:
    """get_ast: no rows -> None."""
    driver = _FakeDriver(select_rows=[])

    assert domain_ast_cst.get_ast(driver, 1) is None


def test_get_ast_parses_json() -> None:
    """get_ast: parses the stored ast_json back into a dict."""
    driver = _FakeDriver(select_rows=[{"ast_json": '{"x": 1}'}])

    assert domain_ast_cst.get_ast(driver, 1) == {"x": 1}


def test_get_ast_bad_json_returns_none() -> None:
    """get_ast: malformed JSON -> None, not an exception."""
    driver = _FakeDriver(select_rows=[{"ast_json": "not json"}])

    assert domain_ast_cst.get_ast(driver, 1) is None


def test_save_cst_inserts_when_no_existing_row() -> None:
    """save_cst: no existing (file_id, cst_hash) row -> INSERT."""
    driver = _FakeDriver(select_rows=[])

    with patch(
        "code_analysis.core.database_driver_pkg.domain.ast_cst.get_file",
        return_value=_fake_file(),
    ):
        result = domain_ast_cst.save_cst(driver, 1, "def f(): pass")

    assert result is True
    assert len(driver.insert_calls) == 1
    assert driver.insert_calls[0][0] == "cst_trees"
