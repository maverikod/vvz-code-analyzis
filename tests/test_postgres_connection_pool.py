"""Tests for PostgreSQLConnectionPool behavior with mocked psycopg."""

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
    """Return mock psycopg module."""
    mod = MagicMock()

    def _connect(**_kwargs: object) -> MagicMock:
        """Return connect."""
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
        """Return connect."""
        c = MagicMock()
        c.autocommit = False
        c.rollback = MagicMock()
        conns.append(c)
        return c

    mod.connect.side_effect = _connect
    return mod, conns


def test_pool_construction_opens_zero_connections(
    mock_psycopg_module: MagicMock,
) -> None:
    """Lazy pool (bug 8e6acb34 follow-up): construction never calls psycopg.connect()."""
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        try:
            assert mock_psycopg_module.connect.call_count == 0
            snap = pool.snapshot()
            assert snap["write"]["capacity"] == 3
            assert snap["read"]["capacity"] == 2
            assert snap["write"]["in_use"] == 0
            assert snap["read"]["in_use"] == 0
            assert snap["write"]["waiters"] == 0
            assert snap["read"]["waiters"] == 0
            assert snap["write"]["established"] == 0
            assert snap["read"]["established"] == 0
        finally:
            pool.close_all()


def test_pool_establishes_exactly_one_connection_per_slot_on_first_use(
    mock_psycopg_module: MagicMock,
) -> None:
    """Each acquire() of a NEW slot connects once; re-acquiring the same slot reuses it."""
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"}, write_pool_size=1)
        try:
            assert mock_psycopg_module.connect.call_count == 0
            with pool.acquire(write=True) as c1:
                pass
            assert mock_psycopg_module.connect.call_count == 1
            assert pool.snapshot()["write"]["established"] == 1
            # Re-acquiring the (single) write slot reuses the same connection
            # -- no second connect().
            with pool.acquire(write=True) as c2:
                assert c2 is c1
            assert mock_psycopg_module.connect.call_count == 1
        finally:
            pool.close_all()


def test_pool_failed_lazy_connect_leaves_slot_retryable(
    mock_psycopg_module: MagicMock,
) -> None:
    """A slot whose first connect() raises is released unestablished, not stuck busy."""
    calls = {"n": 0}

    def _connect(**_kwargs: object) -> MagicMock:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("connection refused")
        c = MagicMock()
        c.autocommit = False
        c.rollback = MagicMock()
        return c

    mock_psycopg_module.connect.side_effect = _connect

    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"}, write_pool_size=1)
        try:
            with pytest.raises(DriverConnectionError) as ei:
                with pool.acquire(write=True):
                    pass
            assert "Failed to lazily establish" in str(ei.value)
            assert isinstance(ei.value.__cause__, OSError)

            # Slot released as unestablished (not busy, not half-open) --
            # snapshot shows idle capacity and no established connection.
            snap = pool.snapshot()
            assert snap["write"]["in_use"] == 0
            assert snap["write"]["idle"] == 1
            assert snap["write"]["established"] == 0

            # A later acquire retries the same slot and succeeds.
            with pool.acquire(write=True) as c:
                assert c is not None
            assert calls["n"] == 2
            assert pool.snapshot()["write"]["established"] == 1
        finally:
            pool.close_all()


def test_acquire_release_marks_idle(mock_psycopg_module: MagicMock) -> None:
    """Verify test acquire release marks idle."""
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
    """Verify test rollback failure raises driver operation."""

    def _connect(**_kwargs: object) -> MagicMock:
        """Return connect."""
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
    """Verify test close all prevents acquire."""
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
    """Verify test four threads share write pool."""
    with patch.dict(sys.modules, {"psycopg": mock_psycopg_module}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        barrier = threading.Barrier(4)
        errors: list[BaseException] = []

        def worker() -> None:
            """Return worker."""
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
    """First write lease lazily connects and maps to write-lane slot 0."""
    mod, conns = _tracking_psycopg_module()
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        try:
            assert len(conns) == 0, "lazy pool: nothing connected until first acquire"
            with pool.acquire(write=True) as c:
                assert c is conns[0]
            assert len(conns) == 1
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
            """Return hold slot0."""
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
    """Read lane is 2 connections; second read uses slot 1 while slot 0 is busy.

    Lazy pool: this test only ever acquires ``write=False``, so no write-lane
    connection is ever established here -- the first two ``psycopg.connect()``
    calls tracked by ``_tracking_psycopg_module`` correspond to read-lane
    slots 0 and 1 (``conns[0]``, ``conns[1]``), not to write-then-read
    construction order as under the old eager-connect pool.
    """
    mod, conns = _tracking_psycopg_module()
    with patch.dict(sys.modules, {"psycopg": mod}):
        from code_analysis.core.database_driver_pkg.drivers.postgres_connection_pool import (
            PostgreSQLConnectionPool,
        )

        pool = PostgreSQLConnectionPool({"dbname": "test"})
        release = threading.Event()

        def hold_read0() -> None:
            """Return hold read0."""
            with pool.acquire(write=False) as c:
                assert c is conns[0]
                release.wait(timeout=5.0)

        tr = threading.Thread(target=hold_read0)
        tr.start()
        time.sleep(0.05)
        try:
            with pool.acquire(write=False) as c:
                assert c is conns[1]
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
            """Return hold write."""
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
            """Return hold three."""
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
            """Return fourth acquire."""
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
        assert len(conns) == 0, "lazy pool: nothing connected until first acquire"
        started = threading.Barrier(3 + 1)
        release_writes = threading.Event()
        errors: list[BaseException] = []

        def hold_write() -> None:
            """Return hold write."""
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
        # All 3 write threads reached the barrier -> each already completed
        # its acquire() (and therefore its lazy connect) before this point,
        # so exactly 3 connections exist now, all write-lane.
        assert len(conns) == 3
        try:
            t0 = time.monotonic()
            with pool.acquire(write=False) as c:
                elapsed = time.monotonic() - t0
                # The read lane has never been touched before this call, so
                # this is deterministically the 4th (and only) connect() so
                # far -- conns[3].
                assert c is conns[3]
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
        """Return hold write."""
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
