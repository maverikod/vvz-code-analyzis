"""
Tests for SQLite driver execute (multi-statement, last result only)
and execute_batch (grouping, order preserved, minimize write commands).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver


@pytest.fixture
def temp_db_path(tmp_path):
    """Temporary database path."""
    return tmp_path / "batch_test.db"


@pytest.fixture
def sqlite_driver(temp_db_path):
    """Connected SQLite driver."""
    driver = SQLiteDriver()
    driver.connect({"path": str(temp_db_path)})
    yield driver
    driver.disconnect()


@pytest.fixture
def table_batch_test(sqlite_driver):
    """Create table batch_test for execute/execute_batch tests."""
    sqlite_driver.execute(
        "CREATE TABLE batch_test (id INTEGER PRIMARY KEY AUTOINCREMENT, x INTEGER)"
    )
    return sqlite_driver


class TestExecuteMultiStatement:
    """execute(): one text can have several statements; return only last result."""

    def test_single_statement_select(self, table_batch_test):
        """Single SELECT returns data."""
        table_batch_test.execute("INSERT INTO batch_test (x) VALUES (1)")
        result = table_batch_test.execute("SELECT * FROM batch_test")
        assert "data" in result
        assert result["data"] is not None
        assert len(result["data"]) == 1
        assert result["data"][0]["x"] == 1

    def test_single_statement_insert_returns_data_none(self, table_batch_test):
        """Single INSERT returns data=None (CRUD)."""
        result = table_batch_test.execute("INSERT INTO batch_test (x) VALUES (1)")
        assert result.get("data") is None
        assert result.get("lastrowid") is not None

    def test_multi_statement_return_last_only_crud(self, table_batch_test):
        """Multiple statements: only last result; last is CRUD -> data=None."""
        result = table_batch_test.execute(
            "INSERT INTO batch_test (x) VALUES (1); INSERT INTO batch_test (x) VALUES (2)"
        )
        assert result.get("data") is None
        assert result.get("affected_rows") == 1
        # First INSERT ran too
        rows = table_batch_test.execute("SELECT * FROM batch_test")
        assert len(rows["data"]) == 2

    def test_multi_statement_return_last_only_select(self, table_batch_test):
        """Multiple statements: only last result; last is SELECT -> data is rows."""
        table_batch_test.execute("INSERT INTO batch_test (x) VALUES (1)")
        result = table_batch_test.execute(
            "INSERT INTO batch_test (x) VALUES (2); SELECT * FROM batch_test"
        )
        assert result.get("data") is not None
        assert len(result["data"]) == 2

    def test_multi_statement_params_apply_to_first(self, table_batch_test):
        """Params apply to first statement only."""
        result = table_batch_test.execute(
            "INSERT INTO batch_test (x) VALUES (?); INSERT INTO batch_test (x) VALUES (99)",
            (42,),
        )
        assert result.get("data") is None
        rows = table_batch_test.execute("SELECT * FROM batch_test ORDER BY id")
        assert len(rows["data"]) == 2
        assert rows["data"][0]["x"] == 42
        assert rows["data"][1]["x"] == 99


class TestExecuteBatchOrderAndGrouping:
    """execute_batch(): one result per statement; order preserved; grouping minimizes writes."""

    def test_batch_one_result_per_statement(self, table_batch_test):
        """Batch returns one result dict per logical statement."""
        ops = [
            ("INSERT INTO batch_test (x) VALUES (?)", (1,)),
            ("INSERT INTO batch_test (x) VALUES (?)", (2,)),
            ("SELECT * FROM batch_test", None),
        ]
        results = table_batch_test.execute_batch(ops)
        assert len(results) == 3
        assert results[0].get("data") is None
        assert results[1].get("data") is None
        assert results[2].get("data") is not None
        assert len(results[2]["data"]) == 2

    def test_batch_crud_elements_have_data_none(self, table_batch_test):
        """CRUD results in the list have data=None."""
        ops = [
            ("INSERT INTO batch_test (x) VALUES (10)", None),
            ("SELECT 1 AS one", None),
        ]
        results = table_batch_test.execute_batch(ops)
        assert results[0]["data"] is None
        assert results[1]["data"] is not None

    def test_batch_multi_statement_in_one_operation(self, table_batch_test):
        """One operation with two statements expands to two results."""
        ops = [
            (
                "INSERT INTO batch_test (x) VALUES (1); INSERT INTO batch_test (x) VALUES (2)",
                None,
            ),
        ]
        results = table_batch_test.execute_batch(ops)
        assert len(results) == 2
        assert results[0]["data"] is None
        assert results[1]["data"] is None
        rows = table_batch_test.execute("SELECT * FROM batch_test")
        assert len(rows["data"]) == 2

    def test_batch_order_preserved_with_mixed_ops(self, table_batch_test):
        """Order of results matches order of statements (mixed INSERT and SELECT)."""
        ops = [
            ("INSERT INTO batch_test (x) VALUES (?)", (1,)),
            ("SELECT * FROM batch_test WHERE x = 1", None),
            ("INSERT INTO batch_test (x) VALUES (?)", (2,)),
            ("SELECT * FROM batch_test", None),
        ]
        results = table_batch_test.execute_batch(ops)
        assert len(results) == 4
        assert results[0]["data"] is None
        assert len(results[1]["data"]) == 1
        assert results[2]["data"] is None
        assert len(results[3]["data"]) == 2

    def test_batch_consecutive_same_sql_grouped_executemany(self, table_batch_test):
        """Consecutive same SQL with params are run as one executemany (minimize writes)."""
        ops = [
            ("INSERT INTO batch_test (x) VALUES (?)", (10,)),
            ("INSERT INTO batch_test (x) VALUES (?)", (20,)),
            ("INSERT INTO batch_test (x) VALUES (?)", (30,)),
        ]
        results = table_batch_test.execute_batch(ops)
        assert len(results) == 3
        for r in results:
            assert r.get("affected_rows") == 1
            assert r.get("data") is None
        rows = table_batch_test.execute("SELECT * FROM batch_test ORDER BY x")
        assert [r["x"] for r in rows["data"]] == [10, 20, 30]

    def test_batch_transaction_id(self, table_batch_test):
        """execute_batch with transaction_id runs in transaction."""
        tid = table_batch_test.begin_transaction()
        ops = [
            ("INSERT INTO batch_test (x) VALUES (?)", (1,)),
            ("SELECT * FROM batch_test", None),
        ]
        results = table_batch_test.execute_batch(ops, transaction_id=tid)
        assert len(results) == 2
        table_batch_test.rollback_transaction(tid)
        rows = table_batch_test.execute("SELECT * FROM batch_test")
        assert len(rows["data"]) == 0


class TestExecuteBatchEdgeCases:
    """Edge cases for execute and execute_batch."""

    def test_execute_empty_statements_returns_safe_result(self, sqlite_driver):
        """Empty or only-whitespace sql returns safe dict with data=None."""
        result = sqlite_driver.execute("  ;  ")
        assert result["data"] is None
        assert "affected_rows" in result

    def test_batch_empty_operations_returns_empty_list(self, table_batch_test):
        """Empty operations list returns empty results."""
        assert table_batch_test.execute_batch([]) == []
