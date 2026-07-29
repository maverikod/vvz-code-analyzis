"""select() pool-routing tests (bug 8e6acb34): read-lane leases, not self.conn.

Covers the four cases the fix's PHASE 3 QA plan calls for:
  (a) select() never touches self.conn/_lock and always acquires write=False.
  (b) the leased read-lane slot is released when the select body raises.
  (c) read-lane exhaustion: the (N+1)th concurrent select blocks then succeeds
      once a slot frees; exceeding max_wait_seconds raises DriverOperationError.
  (d) visibility: insert() on the main-connection path is visible to select()
      on a pooled connection (real PostgreSQL only -- skipped without a DSN).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.drivers.postgres_operations import (
    PostgreSQLOperations,
)
from code_analysis.core.database_driver_pkg.exceptions import DriverOperationError

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


def _driver_with_pool_spy() -> Tuple[PostgreSQLDriver, MagicMock, List[bool], dict]:
    """Return a driver wired to a real PostgreSQLOperations + a spy pool.

    The spy pool records the ``write=`` flag of every ``acquire()`` call and
    counts releases (context-manager exits), without touching real sockets.
    """
    d = PostgreSQLDriver()
    d._schema_tables = {}
    d.conn = MagicMock(name="main_conn")
    d._operations = PostgreSQLOperations(d.conn, {})

    read_conn = MagicMock(name="pooled_read_conn")
    cursor = MagicMock()
    cursor.description = [("id",)]
    cursor.fetchall.return_value = [(1,)]
    read_conn.cursor.return_value = cursor

    acquire_calls: List[bool] = []
    released = {"n": 0}

    @contextmanager
    def _acquire(write: bool = False) -> Any:
        acquire_calls.append(write)
        try:
            yield read_conn
        finally:
            released["n"] += 1

    pool = MagicMock(name="pool_spy")
    pool.acquire = MagicMock(side_effect=lambda write=False: _acquire(write=write))
    d._pool = pool
    return d, read_conn, acquire_calls, released


def test_select_acquires_read_lane_never_touches_main_conn() -> None:
    """(a) select() always acquires write=False and never runs on self.conn."""
    d, read_conn, acquire_calls, released = _driver_with_pool_spy()

    rows = d.select("projects", where={"id": "x"}, columns=["id"])

    assert rows == [{"id": 1}]
    assert acquire_calls == [False]
    d.conn.cursor.assert_not_called()
    d.conn.commit.assert_not_called()
    read_conn.commit.assert_called_once()
    assert released["n"] == 1


def test_select_releases_leased_slot_when_body_raises() -> None:
    """(b) A raising select body still releases the leased slot (finally, not just on success)."""
    d, read_conn, acquire_calls, released = _driver_with_pool_spy()
    read_conn.cursor.side_effect = RuntimeError("boom")

    with pytest.raises(DriverOperationError):
        d.select("projects")

    assert acquire_calls == [False]
    assert released["n"] == 1, "slot must be released even though the body raised"


def _tracking_psycopg_module() -> Tuple[MagicMock, List[MagicMock]]:
    """psycopg mock recording each connection in creation order (write lane first)."""
    conns: List[MagicMock] = []
    mod = MagicMock()

    def _connect(**_kwargs: object) -> MagicMock:
        c = MagicMock()
        c.autocommit = False
        c.rollback = MagicMock()
        conns.append(c)
        return c

    mod.connect.side_effect = _connect
    return mod, conns


def _real_pool_driver(conns: List[MagicMock], pool: Any) -> PostgreSQLDriver:
    """Wire a driver to a real PostgreSQLConnectionPool + real PostgreSQLOperations."""
    d = PostgreSQLDriver()
    d._schema_tables = {}
    d.conn = MagicMock(name="main_conn")
    d._operations = PostgreSQLOperations(d.conn, {})
    d._pool = pool
    return d


def _configure_select_cursor(conn: MagicMock, *, on_execute: Any = None) -> MagicMock:
    """Return a cursor double wired for a successful 1-row select on ``conn``."""
    cursor = MagicMock()
    cursor.description = [("id",)]
    cursor.fetchall.return_value = [(1,)]
    if on_execute is not None:
        cursor.execute.side_effect = on_execute
    conn.cursor.return_value = cursor
    return cursor


def _build_saturatable_pool(
    conns: List[MagicMock], mod: MagicMock, *, max_wait_seconds: float
) -> Any:
    """Construct a real 1-write/2-read pool with mocked psycopg (import-time only).

    ``psycopg`` is mocked ONLY for the constructor's own ``import psycopg`` /
    ``psycopg.connect(...)`` calls -- the returned pool holds plain
    ``MagicMock`` connection objects and needs no further psycopg access.
    Callers must NOT keep ``sys.modules["psycopg"]`` patched while driving
    ``PostgreSQLDriver.select()`` through it: ``postgres.py``'s
    ``_is_connection_lost_error()`` does its own ``import psycopg`` and
    ``isinstance(exc, (psycopg.OperationalError, ...))`` on any exception
    ``select()`` raises (including a genuine pool-timeout ``DriverOperationError``)
    -- with a ``MagicMock`` standing in for the module, ``psycopg.OperationalError``
    is not a real exception type and ``isinstance()`` raises ``TypeError``.
    """
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        return PostgreSQLConnectionPool(
            {"dbname": "test"},
            write_pool_size=1,
            read_pool_size=2,
            max_wait_seconds=max_wait_seconds,
        )


def test_select_read_lane_exhaustion_blocks_then_succeeds() -> None:
    """(c) With read_pool_size=2, a 3rd concurrent select waits, then completes."""
    mod, conns = _tracking_psycopg_module()
    pool = _build_saturatable_pool(conns, mod, max_wait_seconds=5.0)
    try:
        # Construction order: conns[0]=write, conns[1..2]=read lane.
        assert len(conns) == 3
        release_readers = threading.Event()
        both_holding_event = threading.Event()
        lock = threading.Lock()
        call_count = {"n": 0}

        def blocking_execute(*_a: object, **_k: object) -> None:
            with lock:
                call_count["n"] += 1
                n = call_count["n"]
            if n <= 2:
                if n == 2:
                    both_holding_event.set()
                release_readers.wait(timeout=5.0)
            # 3rd+ call: release_readers is already set by the time any
            # further select reaches here, so it falls straight through.

        _configure_select_cursor(conns[1], on_execute=blocking_execute)
        _configure_select_cursor(conns[2], on_execute=blocking_execute)

        d = _real_pool_driver(conns, pool)
        errors: List[BaseException] = []

        def holder() -> None:
            try:
                d.select("projects")
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        holders = [threading.Thread(target=holder) for _ in range(2)]
        for t in holders:
            t.start()
        assert both_holding_event.wait(timeout=5.0)  # both readers now inside execute()

        assert pool.snapshot()["read"]["in_use"] == 2

        third_done = threading.Event()
        third_result: dict = {}

        def third() -> None:
            t0 = time.monotonic()
            third_result["rows"] = d.select("projects")
            third_result["elapsed"] = time.monotonic() - t0
            third_done.set()

        t3 = threading.Thread(target=third)
        t3.start()
        time.sleep(0.15)
        # Third select must still be waiting for a free read slot.
        assert not third_done.is_set()
        assert pool.snapshot()["read"]["waiters"] >= 1

        release_readers.set()
        for t in holders:
            t.join(timeout=5.0)
            assert not t.is_alive()
        assert third_done.wait(timeout=5.0)
        t3.join(timeout=5.0)

        assert errors == []
        assert third_result["rows"] == [{"id": 1}]
    finally:
        pool.close_all()


def test_select_read_lane_timeout_raises_driver_operation_error() -> None:
    """(c) Exceeding max_wait_seconds on a saturated read lane raises DriverOperationError."""
    mod, conns = _tracking_psycopg_module()
    pool = _build_saturatable_pool(conns, mod, max_wait_seconds=0.12)
    try:
        assert len(conns) == 3
        release_readers = threading.Event()
        both_holding_event = threading.Event()
        lock = threading.Lock()
        call_count = {"n": 0}

        def blocking_execute(*_a: object, **_k: object) -> None:
            with lock:
                call_count["n"] += 1
                n = call_count["n"]
            if n <= 2:
                if n == 2:
                    both_holding_event.set()
                release_readers.wait(timeout=5.0)

        _configure_select_cursor(conns[1], on_execute=blocking_execute)
        _configure_select_cursor(conns[2], on_execute=blocking_execute)

        d = _real_pool_driver(conns, pool)
        errors: List[BaseException] = []

        def holder() -> None:
            try:
                d.select("projects")
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        holders = [threading.Thread(target=holder) for _ in range(2)]
        for t in holders:
            t.start()
        assert both_holding_event.wait(timeout=5.0)

        try:
            with pytest.raises(DriverOperationError) as ei:
                d.select("projects")
            assert "timeout" in str(ei.value).lower()
        finally:
            release_readers.set()
            for t in holders:
                t.join(timeout=5.0)
                assert not t.is_alive()
            assert errors == []
    finally:
        pool.close_all()


@pytest.mark.postgres
@pytest.mark.integration
def test_select_via_pool_sees_row_inserted_on_main_connection_real_pg() -> None:
    """(d) Visibility: insert() (main conn) then select() (pooled read conn) sees the row.

    Optional live PostgreSQL check. CI: set ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` to a
    disposable database; without it the test is skipped so default pipelines stay
    green without Postgres. Exercises the exact routing this bug fixes: insert()
    still runs on the driver's main connection under ``self._lock``, select() now
    runs on a leased read-lane connection -- READ COMMITTED means the insert's
    commit (postgres_operations.insert() commits before returning) must be
    visible to a subsequent select() on a different connection.
    """
    dsn = (os.environ.get(_PG_ENV) or "").strip()
    if not dsn:
        pytest.skip(
            f"Live PostgreSQL select-pool visibility test skipped: set {_PG_ENV} to run."
        )

    import uuid

    d = PostgreSQLDriver()
    d.connect({"dsn": dsn})
    try:
        project_id = str(uuid.uuid4())
        pk = d.insert(
            "projects",
            {
                "id": project_id,
                "server_instance_id": str(uuid.uuid4()),
                "name": f"select-pool-visibility-{project_id[:8]}",
                "root_path": "/tmp/does-not-exist",
            },
        )
        assert pk is not None
        rows = d.select("projects", where={"id": project_id})
        assert len(rows) == 1
        assert rows[0]["id"] == project_id
    finally:
        try:
            d.delete("projects", where={"id": project_id})
        except Exception:
            pass
        d.disconnect()
