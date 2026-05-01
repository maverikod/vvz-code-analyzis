# PostgreSQLConnectionPool behavior (mocked psycopg, no live server).

from __future__ import annotations

import os
import sys
import threading
import time
from typing import List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.exceptions import (
    DriverConnectionError,
    DriverOperationError,
)

_PG_ENV = "CODE_ANALYSIS_POSTGRES_TEST_DSN"


@pytest.fixture()
def mock_psycopg_module() -> MagicMock:
    mod = MagicMock()

    def _connect(**_kwargs: object) -> MagicMock:
        c = MagicMock()
        c.autocommit = False
        c.rollback = MagicMock()
        return c

    mod.connect.side_effect = _connect
    return mod


def _tracking_psycopg_module() -> Tuple[MagicMock, List[MagicMock]]:
    """psycopg mock that records each connection object in creation order (3 write, 2 read)."""
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


def test_pool_opens_five_connections(mock_psycopg_module: MagicMock) -> None:
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        try:
            assert mock_psycopg_module.connect.call_count == 5
            snap = pool.snapshot()
            assert snap["write"]["capacity"] == 3
            assert snap["read"]["capacity"] == 2
            assert snap["write"]["in_use"] == 0
            assert snap["read"]["in_use"] == 0
            assert snap["write"]["waiters"] == 0
            assert snap["read"]["waiters"] == 0
        finally:
            pool.close_all()


def test_acquire_release_marks_idle(mock_psycopg_module: MagicMock) -> None:
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        try:
            with pool.acquire(write=True):
                s = pool.snapshot()
                assert s["write"]["in_use"] == 1
            assert pool.snapshot()["write"]["in_use"] == 0
        finally:
            pool.close_all()


def test_rollback_failure_raises_driver_operation(
    mock_psycopg_module: MagicMock,
) -> None:
    def _connect(**_kwargs: object) -> MagicMock:
        c = MagicMock()
        c.autocommit = False
        c.rollback.side_effect = OSError("rb fail")
        return c

    mock_psycopg_module.connect.side_effect = _connect

    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        try:
            with pytest.raises(DriverOperationError) as ei:
                with pool.acquire(write=False):
                    raise RuntimeError("stmt failed")
            assert "Rollback before database retry failed" in str(ei.value)
            assert isinstance(ei.value.__cause__, OSError)
        finally:
            pool.close_all()


def test_close_all_prevents_acquire(mock_psycopg_module: MagicMock) -> None:
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        pool.close_all()
        with pytest.raises(DriverConnectionError):
            with pool.acquire(write=True):
                pass


def test_four_threads_share_write_pool(mock_psycopg_module: MagicMock) -> None:
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        barrier = threading.Barrier(4)
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                barrier.wait()
                with pool.acquire(write=True):
                    time.sleep(0.02)
            except BaseException as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive()
        try:
            assert errors == []
        finally:
            pool.close_all()


def test_first_free_write_uses_lowest_slot() -> None:
    """First write lease maps to the first built connection (index 0 in write lane)."""
    mod, conns = _tracking_psycopg_module()
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        try:
            assert len(conns) == 5
            with pool.acquire(write=True) as c:
                assert c is conns[0]
        finally:
            pool.close_all()


def test_first_free_write_skips_busy_lower_index() -> None:
    """While slot 0 is held, the next write lease takes slot 1 (first-free, not FIFO queue)."""
    mod, conns = _tracking_psycopg_module()
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        release = threading.Event()

        def hold_slot0() -> None:
            with pool.acquire(write=True) as c:
                assert c is conns[0]
                release.wait(timeout=5.0)

        t0 = threading.Thread(target=hold_slot0)
        t0.start()
        time.sleep(0.05)
        try:
            with pool.acquire(write=True) as c:
                assert c is conns[1]
        finally:
            release.set()
            t0.join(timeout=5.0)
            pool.close_all()


def test_first_free_read_skips_busy_lower_index() -> None:
    """Read lane is 2 connections; second read uses index 1 while index 0 is busy."""
    mod, conns = _tracking_psycopg_module()
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        # conns[3], conns[4] are read pool in construction order
        release = threading.Event()

        def hold_read0() -> None:
            with pool.acquire(write=False) as c:
                assert c is conns[3]
                release.wait(timeout=5.0)

        tr = threading.Thread(target=hold_read0)
        tr.start()
        time.sleep(0.05)
        try:
            with pool.acquire(write=False) as c:
                assert c is conns[4]
        finally:
            release.set()
            tr.join(timeout=5.0)
            pool.close_all()


def test_acquire_write_timeout_when_all_slots_busy(
    mock_psycopg_module: MagicMock,
) -> None:
    """Fourth write waiter gets DriverOperationError after max_wait_seconds."""
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"}, max_wait_seconds=0.12)
        release = threading.Event()

        def hold_write() -> None:
            with pool.acquire(write=True):
                release.wait(timeout=5.0)

        threads = [threading.Thread(target=hold_write) for _ in range(3)]
        for t in threads:
            t.start()
        time.sleep(0.05)
        try:
            with pytest.raises(DriverOperationError) as ei:
                with pool.acquire(write=True):
                    pass
            assert "timeout" in str(ei.value).lower()
        finally:
            release.set()
            for t in threads:
                t.join(timeout=5.0)
                assert not t.is_alive()
            pool.close_all()


def test_snapshot_reports_nonzero_write_waiters(mock_psycopg_module: MagicMock) -> None:
    """While a fourth write blocks in wait(), snapshot reports write waiters >= 1."""
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"}, max_wait_seconds=3.0)
        release_holders = threading.Event()
        three_holding = threading.Event()
        hold_lock = threading.Lock()
        holding_state = {"n": 0}

        def hold_three() -> None:
            with pool.acquire(write=True):
                with hold_lock:
                    holding_state["n"] += 1
                    if holding_state["n"] == 3:
                        three_holding.set()
                release_holders.wait(timeout=10.0)

        holders = [threading.Thread(target=hold_three) for _ in range(3)]
        for h in holders:
            h.start()
        assert three_holding.wait(timeout=5.0)

        def fourth_acquire() -> None:
            with pool.acquire(write=True):
                pass

        t4 = threading.Thread(target=fourth_acquire)
        t4.start()
        time.sleep(0.15)
        waiters_observed: list[int] = []
        try:
            snap = pool.snapshot()
            waiters_observed.append(int(snap["write"]["waiters"]))
        finally:
            release_holders.set()
            t4.join(timeout=5.0)
            for h in holders:
                h.join(timeout=5.0)
            pool.close_all()

        assert (
            waiters_observed[-1] >= 1
        ), f"expected waiters>=1, got {waiters_observed!r}"


def test_read_lease_not_blocked_when_all_write_slots_busy() -> None:
    """
    list_projects-style read path: read pool is independent of write pool.

    While three workers hold all write connections (long), acquiring a read
    slot still completes without waiting for those writes (mocked connections).
    """
    mod, conns = _tracking_psycopg_module()
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        assert len(conns) == 5
        started = threading.Barrier(3 + 1)
        release_writes = threading.Event()
        errors: list[BaseException] = []

        def hold_write() -> None:
            try:
                with pool.acquire(write=True):
                    started.wait()
                    release_writes.wait(timeout=10.0)
            except BaseException as e:
                errors.append(e)

        threads = [threading.Thread(target=hold_write) for _ in range(3)]
        for t in threads:
            t.start()
        started.wait(timeout=5.0)
        try:
            t0 = time.monotonic()
            with pool.acquire(write=False) as c:
                elapsed = time.monotonic() - t0
                assert c is conns[3] or c is conns[4]
                assert (
                    elapsed < 0.8
                ), "read acquire should not wait for long write lane when read idle"
        finally:
            release_writes.set()
            for t in threads:
                t.join(timeout=5.0)
                assert not t.is_alive()
            assert errors == []
            pool.close_all()


@pytest.mark.postgres
@pytest.mark.integration
def test_live_pg_pool_read_not_blocked_when_writes_saturated() -> None:
    """
    Optional live PostgreSQL check for Phase 1 step 7.

    CI: run with ``CODE_ANALYSIS_POSTGRES_TEST_DSN`` set to a disposable DB; without
    it the test is skipped so default pipelines stay green without Postgres.

    Opens a real 3+2 pool, holds three write leases in threads, and asserts a read
    lease (analogous to list_projects) is taken quickly.
    """
    dsn = (os.environ.get(_PG_ENV) or "").strip()
    if not dsn:
        pytest.skip(
            f"Live PostgreSQL pool test skipped: set {_PG_ENV} to run (optional CI)."
        )

    import psycopg

    from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
        PostgreSQLConnectionPool,
    )

    try:
        kwargs = psycopg.conninfo.conninfo_to_dict(dsn)
    except Exception:
        kwargs = {"conninfo": dsn}

    pool = PostgreSQLConnectionPool(kwargs)
    release_writes = threading.Event()
    errors: list[BaseException] = []

    def hold_write() -> None:
        try:
            with pool.acquire(write=True):
                release_writes.wait(timeout=60.0)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=hold_write) for _ in range(3)]
    try:
        for t in threads:
            t.start()
        time.sleep(0.15)
        t0 = time.monotonic()
        with pool.acquire(write=False) as conn:
            elapsed = time.monotonic() - t0
            conn.execute("SELECT 1")
        assert (
            elapsed < 2.0
        ), "read pool should serve while write pool busy (real Postgres 3+2 pool)"
    finally:
        release_writes.set()
        for t in threads:
            t.join(timeout=10.0)
            assert not t.is_alive()
        assert errors == []
        pool.close_all()
