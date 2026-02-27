"""
Tests for SQLite driver batch parsing and grouping.

Verifies: split_batch_sql, expand_operations, group_for_executemany.
Order is preserved; consecutive same-SQL are grouped for native executemany
to minimize write commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.database_driver_pkg.drivers.sqlite_batch import (
    expand_operations,
    group_for_executemany,
    run_batch_result_counts,
    split_batch_sql,
)


class TestSplitBatchSql:
    """Test splitting SQL text into statements by semicolon."""

    def test_empty_string(self):
        """Empty or whitespace returns empty list."""
        assert split_batch_sql("") == []
        assert split_batch_sql("   ") == []
        assert split_batch_sql("\n\t") == []

    def test_single_statement(self):
        """Single statement without semicolon returns one element."""
        assert split_batch_sql("SELECT 1") == ["SELECT 1"]
        assert split_batch_sql("  INSERT INTO t VALUES (1)  ") == [
            "INSERT INTO t VALUES (1)"
        ]

    def test_multiple_statements(self):
        """Semicolon separates statements; stripped."""
        assert split_batch_sql("SELECT 1; SELECT 2") == ["SELECT 1", "SELECT 2"]
        assert split_batch_sql("CREATE TABLE t (a INT); INSERT INTO t VALUES (1)") == [
            "CREATE TABLE t (a INT)",
            "INSERT INTO t VALUES (1)",
        ]

    def test_trailing_semicolon(self):
        """Trailing semicolon yields empty last part which is skipped."""
        assert split_batch_sql("SELECT 1;") == ["SELECT 1"]
        assert split_batch_sql("SELECT 1; SELECT 2;") == ["SELECT 1", "SELECT 2"]

    def test_multiple_semicolons_empty_parts(self):
        """Empty parts between semicolons are skipped."""
        assert split_batch_sql("SELECT 1;; SELECT 2") == ["SELECT 1", "SELECT 2"]


class TestExpandOperations:
    """Test expanding (sql, params) into flat (stmt, params) list."""

    def test_empty(self):
        """Empty operations -> empty list."""
        assert expand_operations([]) == []

    def test_single_one_statement(self):
        """One operation with one statement stays one."""
        assert expand_operations([("SELECT 1", None)]) == [("SELECT 1", None)]

    def test_single_multi_statement(self):
        """One operation with two statements expands to two; params only on first."""
        got = expand_operations([("SELECT 1; SELECT 2", ())])
        assert got == [("SELECT 1", ()), ("SELECT 2", None)]

    def test_multi_statement_with_params(self):
        """Params apply to first statement only."""
        got = expand_operations([("INSERT INTO t VALUES (?); DELETE FROM t", (1,))])
        assert got == [
            ("INSERT INTO t VALUES (?)", (1,)),
            ("DELETE FROM t", None),
        ]

    def test_multiple_operations(self):
        """Order preserved across operations."""
        ops = [
            ("SELECT 1", None),
            ("INSERT INTO t VALUES (?); INSERT INTO t VALUES (?)", (1,)),
        ]
        got = expand_operations(ops)
        assert got == [
            ("SELECT 1", None),
            ("INSERT INTO t VALUES (?)", (1,)),
            ("INSERT INTO t VALUES (?)", None),
        ]


class TestGroupForExecutemany:
    """Test grouping consecutive same-SQL for native batch (minimize write commands)."""

    def test_empty(self):
        """Empty expanded list -> empty runs."""
        assert group_for_executemany([]) == []

    def test_single_item(self):
        """One (sql, params) -> one single run."""
        assert group_for_executemany([("SELECT 1", None)]) == [
            ("single", ("SELECT 1", None))
        ]
        assert group_for_executemany([("INSERT INTO t VALUES (?)", (1,))]) == [
            ("single", ("INSERT INTO t VALUES (?)", (1,)))
        ]

    def test_consecutive_same_sql_with_params_grouped(self):
        """Consecutive same SQL with params -> one 'many' run (minimize writes)."""
        expanded = [
            ("INSERT INTO t (x) VALUES (?)", (1,)),
            ("INSERT INTO t (x) VALUES (?)", (2,)),
            ("INSERT INTO t (x) VALUES (?)", (3,)),
        ]
        runs = group_for_executemany(expanded)
        assert len(runs) == 1
        assert runs[0][0] == "many"
        assert runs[0][1][0] == "INSERT INTO t (x) VALUES (?)"
        assert runs[0][1][1] == [(1,), (2,), (3,)]

    def test_order_preserved_different_sql(self):
        """Different SQL -> separate runs; order preserved."""
        expanded = [
            ("INSERT INTO t (x) VALUES (?)", (1,)),
            ("SELECT 1", None),
            ("INSERT INTO t (x) VALUES (?)", (2,)),
        ]
        runs = group_for_executemany(expanded)
        assert len(runs) == 3
        assert runs[0] == ("single", ("INSERT INTO t (x) VALUES (?)", (1,)))
        assert runs[1] == ("single", ("SELECT 1", None))
        assert runs[2] == ("single", ("INSERT INTO t (x) VALUES (?)", (2,)))

    def test_same_sql_then_none_params_breaks_group(self):
        """Consecutive same SQL but one has params=None -> group then single."""
        expanded = [
            ("INSERT INTO t (x) VALUES (?)", (1,)),
            ("INSERT INTO t (x) VALUES (?)", (2,)),
            ("INSERT INTO t (x) VALUES (?)", None),  # no params
        ]
        runs = group_for_executemany(expanded)
        assert len(runs) == 2
        assert runs[0] == ("many", ("INSERT INTO t (x) VALUES (?)", [(1,), (2,)]))
        assert runs[1] == ("single", ("INSERT INTO t (x) VALUES (?)", None))

    def test_two_groups_of_same_sql(self):
        """Two separate groups of same-SQL -> two 'many' runs."""
        expanded = [
            ("INSERT INTO t (x) VALUES (?)", (1,)),
            ("INSERT INTO t (x) VALUES (?)", (2,)),
            ("SELECT 1", None),
            ("INSERT INTO t (x) VALUES (?)", (3,)),
            ("INSERT INTO t (x) VALUES (?)", (4,)),
        ]
        runs = group_for_executemany(expanded)
        assert len(runs) == 3
        assert runs[0] == ("many", ("INSERT INTO t (x) VALUES (?)", [(1,), (2,)]))
        assert runs[1] == ("single", ("SELECT 1", None))
        assert runs[2] == ("many", ("INSERT INTO t (x) VALUES (?)", [(3,), (4,)]))


class TestRunBatchResultCounts:
    """Test result count per run (for ordering)."""

    def test_empty(self):
        """Empty runs -> empty counts."""
        assert run_batch_result_counts([]) == []

    def test_single_runs(self):
        """Each single run produces 1 result."""
        runs = [
            ("single", ("SELECT 1", None)),
            ("single", ("INSERT INTO t VALUES (1)", None)),
        ]
        assert run_batch_result_counts(runs) == [1, 1]

    def test_many_run(self):
        """One many run with N params produces N results."""
        runs = [("many", ("INSERT INTO t (x) VALUES (?)", [(1,), (2,), (3,)]))]
        assert run_batch_result_counts(runs) == [3]
