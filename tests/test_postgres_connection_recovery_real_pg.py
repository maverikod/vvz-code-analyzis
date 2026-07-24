"""
Real-PostgreSQL and fast unit regression tests for the connection-poisoning defect
in ``code_analysis/core/database_driver_pkg/drivers/postgres_run.py`` (bug bb0b6ace):

    "Project unreachable immediately after rename_project, recovers later
    (transient post-write visibility; suspected connection-poisoning in
    run_execute_batch)"

Root cause: ``run_execute`` / ``run_execute_batch`` used to have

    except TransientDatabaseError:
        raise
    except DriverOperationError:
        raise
    except Exception as e:
        if not transaction_id:
            try:
                conn.rollback()
            except Exception:
                pass
        _raise_classified(e, ...)

The first two branches re-raised BEFORE the ``conn.rollback()`` in the general
handler ever ran. Any failure that was already classified to
``TransientDatabaseError``/``DriverOperationError`` *before* reaching this outer
try/except -- which is exactly what happens for an ``executemany`` run inside
``run_execute_batch`` (see the ``pg_errors``/``_raise_classified`` handling in the
"many" branch) -- therefore skipped rollback entirely. A self-managed
(``transaction_id`` falsy) connection was handed back to its caller (in
production: the write/read pool) still sitting in PostgreSQL's aborted-transaction
state, so the NEXT statement on that same connection failed with
"current transaction is aborted, commands ignored until end of transaction
block" -- until something eventually rolled it back. This is the plausible
mechanism behind bug bb0b6ace (N2: project transiently unreachable right after
rename_project) and a suspected contributor to N1 (content_stale search-visibility
gaps): a batch DML failure poisons a connection that a subsequent read then
borrows.

The fix: both ``except`` branches now roll back (when ``not transaction_id``,
matching the existing rollback-scope convention) before re-raising, exactly like
the general-exception branch always did.

Real-PG tests require ``CODE_ANALYSIS_POSTGRES_TEST_DSN``; skipped when unset,
same optional live-PostgreSQL convention as the sibling
``test_postgres_file_sync_dml_real_pg.py`` / ``test_postgres_schema_bootstrap_real_pg.py``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Iterator, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from code_analysis.core.database_driver_pkg.exceptions import (
    DriverOperationError,
    TransientDatabaseError,
)

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _live_dsn() -> str:
    dsn = (os.environ.get(_PG_ENV) or "").strip()
    if not dsn:
        pytest.skip(
            f"Live PostgreSQL test skipped: set {_PG_ENV} to run (optional CI)."
        )
    return dsn


@pytest.fixture()
def fresh_pg_schema_conn() -> Iterator[Any]:
    """Open connection with an isolated, empty PostgreSQL schema as sole search_path.

    Same pattern as ``test_postgres_file_sync_dml_real_pg.py``'s fixture
    (duplicated rather than shared, matching this test suite's existing
    one-fixture-per-file convention for the real-PG test modules).
    """
    pytest.importorskip("psycopg")
    import psycopg

    dsn = _live_dsn()
    schema_name = f"catest_{uuid.uuid4().hex[:16]}"
    conn = psycopg.connect(dsn)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema_name}")
        cur.execute(f"SET search_path TO {schema_name}")
    conn.commit()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            conn.commit()
        finally:
            conn.close()


def _make_pk_table(conn: Any, table_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()


# Two operations with IDENTICAL sql text and non-None params: sql_batch_grouping's
# group_for_executemany merges them into one ("many", (sql, [params...])) run, which
# is executed via ``cursor.executemany`` -- the branch whose failures are classified
# to TransientDatabaseError/DriverOperationError INSIDE the loop (postgres_run.py's
# ``pg_errors``/``_raise_classified`` handling), i.e. exactly the shape that hit the
# raise-before-rollback bug. The second row's id collides with the first -> a genuine
# PostgreSQL unique-violation raised mid-executemany.
def _poisoning_ops(table_name: str) -> List[Tuple[str, Optional[tuple]]]:
    sql = f"INSERT INTO {table_name} (id, val) VALUES (?, ?)"
    return [
        (sql, (1, "a")),
        (sql, (1, "b")),  # duplicate PK -> IntegrityError inside executemany
    ]


@pytest.mark.postgres
@pytest.mark.integration
def test_execute_batch_failure_does_not_poison_connection_real_postgres(
    fresh_pg_schema_conn: Any,
) -> None:
    """Non-vacuous proof (FIXED code): an execute_batch failure on a connection
    rolls it back before propagating, so a SECOND, unrelated query on that same
    connection (standing in for the next command that borrows it from the pool)
    succeeds cleanly -- no aborted-transaction poisoning survives the error."""
    conn = fresh_pg_schema_conn
    _make_pk_table(conn, "poison_t1")

    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    with pytest.raises(DriverOperationError):
        postgres_run.run_execute_batch(
            conn, _poisoning_ops("poison_t1"), None, None, {}
        )

    # Second, unrelated query on the SAME connection: must succeed. Pre-fix this
    # raised psycopg.errors.InFailedSqlTransaction ("current transaction is
    # aborted, commands ignored until end of transaction block").
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


@pytest.mark.postgres
@pytest.mark.integration
def test_prefix_shape_reproduces_poisoning_on_real_postgres(
    fresh_pg_schema_conn: Any,
) -> None:
    """Non-vacuous proof (PRE-FIX shape): replaying the ORIGINAL buggy except-order
    (raise before rollback for TransientDatabaseError/DriverOperationError) against
    a real PostgreSQL server reproduces the exact poisoning symptom -- the second
    query fails with 'current transaction is aborted'. This is the same scenario
    the test above proves is now fixed; keeping both pins the regression to the
    genuine incident mechanism rather than an unrelated assertion."""
    conn = fresh_pg_schema_conn
    _make_pk_table(conn, "poison_t2")

    from code_analysis.core.database_driver_pkg.drivers import postgres_run
    from code_analysis.core.database_driver_pkg.drivers.sql_batch_grouping import (
        expand_operations,
        group_for_executemany,
    )

    # Minimal re-implementation of the PRE-FIX run_execute_batch tail: identical
    # up through classification, but re-raises immediately on
    # TransientDatabaseError/DriverOperationError WITHOUT the rollback the fixed
    # code now performs in that branch.
    def _pre_fix_run_execute_batch(
        conn: Any, operations: List[Tuple[str, Optional[tuple]]]
    ) -> None:
        expanded = expand_operations(operations)
        runs = group_for_executemany(expanded)
        pg_errors: Any = None
        try:
            from psycopg import errors as pg_errors  # noqa: F811
        except ImportError:
            pass
        try:
            for kind, payload in runs:
                assert kind == "many"
                sql, params_list = payload
                assert params_list  # non-empty for this test's fixed operations
                sql_pg, _ = postgres_run._sqlite_qmarks_to_psycopg(
                    postgres_run._adapt_sqlite_dml_for_postgres(sql), params_list[0]
                )
                cursor = conn.cursor()
                try:
                    try:
                        cursor.executemany(sql_pg, params_list)
                    except Exception as ie:
                        if pg_errors and isinstance(ie, pg_errors.IntegrityError):
                            raise DriverOperationError(
                                f"execute_batch failed: {ie}"
                            ) from ie
                        raise
                finally:
                    cursor.close()
            conn.commit()
        except TransientDatabaseError:
            raise
        except DriverOperationError:
            raise  # <-- pre-fix bug: no conn.rollback() on this path
        except Exception:
            conn.rollback()
            raise

    with pytest.raises(DriverOperationError):
        _pre_fix_run_execute_batch(conn, _poisoning_ops("poison_t2"))

    import psycopg

    with pytest.raises(psycopg.errors.InFailedSqlTransaction):
        with conn.cursor() as cur:
            cur.execute("SELECT 1")


# --- Fast, DB-free unit tests: assert rollback is called before the exception
# propagates, for every raise-before-rollback shape in both run_execute and
# run_execute_batch. These do not need a live PostgreSQL server.


def _mock_conn_cursor_raises(exc: BaseException) -> MagicMock:
    """Mock connection whose cursor().execute() raises ``exc`` immediately."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = exc
    conn.cursor.return_value = cursor
    return conn


def test_run_execute_rolls_back_before_raising_transient_database_error() -> None:
    """run_execute must roll back a self-managed connection before a
    TransientDatabaseError (already-classified inside the try) propagates."""
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    conn = _mock_conn_cursor_raises(
        TransientDatabaseError(
            "boom", sqlstate="40P01", error_kind="deadlock", retryable=True
        )
    )
    with pytest.raises(TransientDatabaseError):
        postgres_run.run_execute(conn, "SELECT 1", None, None, None, {})
    conn.rollback.assert_called_once()


def test_run_execute_rolls_back_before_raising_driver_operation_error() -> None:
    """Same invariant for the DriverOperationError branch."""
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    conn = _mock_conn_cursor_raises(DriverOperationError("boom"))
    with pytest.raises(DriverOperationError):
        postgres_run.run_execute(conn, "SELECT 1", None, None, None, {})
    conn.rollback.assert_called_once()


def test_run_execute_batch_rolls_back_before_raising_driver_operation_error() -> None:
    """run_execute_batch's ``executemany`` branch classifies IntegrityError to
    DriverOperationError INSIDE the loop (before the outer try/except sees it) --
    this is the exact shape that hit bug bb0b6ace. Rollback must still run."""
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    conn = MagicMock()
    cursor = MagicMock()
    cursor.executemany.side_effect = DriverOperationError(
        "execute_batch failed: boom"
    )
    conn.cursor.return_value = cursor

    ops: List[Tuple[str, Optional[tuple]]] = [
        ("INSERT INTO t (id, val) VALUES (?, ?)", (1, "a")),
        ("INSERT INTO t (id, val) VALUES (?, ?)", (2, "b")),
    ]
    with pytest.raises(DriverOperationError):
        postgres_run.run_execute_batch(conn, ops, None, None, {})
    conn.rollback.assert_called_once()


def test_run_execute_batch_rolls_back_before_raising_transient_database_error() -> None:
    """Same invariant for a TransientDatabaseError raised out of the executemany
    branch (e.g. a deadlock classified via ``_raise_classified``)."""
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    conn = MagicMock()
    cursor = MagicMock()
    cursor.executemany.side_effect = TransientDatabaseError(
        "boom", sqlstate="40P01", error_kind="deadlock", retryable=True
    )
    conn.cursor.return_value = cursor

    ops: List[Tuple[str, Optional[tuple]]] = [
        ("INSERT INTO t (id, val) VALUES (?, ?)", (1, "a")),
        ("INSERT INTO t (id, val) VALUES (?, ?)", (2, "b")),
    ]
    with pytest.raises(TransientDatabaseError):
        postgres_run.run_execute_batch(conn, ops, None, None, {})
    conn.rollback.assert_called_once()


def test_run_execute_batch_no_rollback_when_transaction_id_set() -> None:
    """When ``transaction_id`` is truthy (external, caller-managed transaction),
    run_execute_batch must NOT roll back itself -- that stays the transaction
    owner's job (``PostgreSQLDriver.execute_logical_write_operation`` /
    ``PostgreSQLTransactionManager``). Only the ``not transaction_id`` gate
    changed here, not this pre-existing convention."""
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    conn = MagicMock()
    cursor = MagicMock()
    cursor.executemany.side_effect = DriverOperationError("boom")
    conn.cursor.return_value = cursor

    ops: List[Tuple[str, Optional[tuple]]] = [
        ("INSERT INTO t (id, val) VALUES (?, ?)", (1, "a")),
        ("INSERT INTO t (id, val) VALUES (?, ?)", (2, "b")),
    ]
    with pytest.raises(DriverOperationError):
        postgres_run.run_execute_batch(conn, ops, "some-real-transaction-id", None, {})
    conn.rollback.assert_not_called()
