"""
Thread-safe PostgreSQL connection pool: configurable write + read lanes.

Lane sizes (first-free slot per lane) are set by the ``write_pool_size`` /
``read_pool_size`` constructor parameters; this class's own parameter defaults
(3 write, 2 read) are a bare-minimum fallback for direct/test instantiation.
Production always passes both explicitly -- ``PostgreSQLDriver.connect()``
wires them from ``config.json``'s ``pool_write_size`` / ``pool_read_size``,
whose *own* defaults are 3 write + 12 read. The read lane's effective default
was raised from 2 to 12 by bug 8e6acb34's fix (that change lives in
``postgres.py``, not here): the offload worker pool allows up to
``min(32, cpu_count*4)`` concurrent commands, each running a project-scoped
lock-gate ``select()`` before its body, plus ordinary read RPCs (e.g.
``full_text_search``) that were already routed here via ``execute()``.

Used only for **self-managed** driver work (no external ``transaction_id``, or
``transaction_id=\"local\"``). Explicit RPC transactions use separate connections
via ``PostgreSQLTransactionManager`` and do not lease from this pool. ``select()``
joined ``execute()`` / ``execute_batch()`` on this pool's read lane as of bug
8e6acb34 (previously ``select()`` ran on the driver's single main connection
under an unbounded lock, serializing every project-scoped command process-wide).

**Contention:** if all write connections are busy with long-running
self-managed writes, ``acquire(write=True)`` waits up to ``max_wait_seconds`` (default
30s) for a slot, then raises ``DriverOperationError``. The read connections
are independent; read traffic can proceed while writes are saturated, subject to DB
locks and SQL semantics.

**HARD INVARIANT -- no nested acquire.** A caller must never call ``acquire()``
on this pool while it already holds a connection leased from the *same* pool
instance (whether from the same or the other lane). Each lane hands out its
``pool_size`` connections and blocks the caller until one frees; a thread that
tries to acquire a second connection while sitting inside its own ``with
acquire(...)`` block can deadlock the pool once the lane is saturated (that
thread occupies one slot and blocks forever waiting for another, which can
only free if the deadlocked thread itself releases -- it cannot). Every
production call site (``PostgreSQLDriver.execute``, ``.execute_batch``,
``.select`` / ``._select_via_pool``) acquires exactly once per call and
returns/raises before the ``with`` block exits; none call back into
``self._pool`` while already inside one of their own ``with pool.acquire(...)``
blocks. Verified by grep across the driver package (2026-07): the only
``pool.acquire(`` call sites are those three, each a single, non-nested lease.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from ..exceptions import DriverConnectionError, DriverOperationError

logger = logging.getLogger(__name__)


class PostgreSQLConnectionPool:
    """Configurable write/read lanes (default 3 write, 2 read); first idle slot per lane."""

    def __init__(
        self,
        connect_kwargs: Dict[str, Any],
        *,
        max_wait_seconds: float = 30.0,
        write_pool_size: int = 3,
        read_pool_size: int = 2,
    ) -> None:
        """Initialize the instance.

        :param connect_kwargs: keyword arguments passed to ``psycopg.connect``
            for every lane connection.
        :param max_wait_seconds: how long ``acquire`` waits for a free slot
            before raising ``DriverOperationError``.
        :param write_pool_size: number of write-lane connections (default 3);
            must be >= 1.
        :param read_pool_size: number of read-lane connections (default 2);
            must be >= 1.
        """
        if write_pool_size < 1 or read_pool_size < 1:
            raise DriverConnectionError(
                "PostgreSQL pool lane sizes must be >= 1 "
                f"(got write_pool_size={write_pool_size}, "
                f"read_pool_size={read_pool_size}); both lanes need at least "
                "one connection"
            )
        try:
            import psycopg
        except ImportError as e:
            raise DriverConnectionError(
                "PostgreSQL pool requires psycopg (pip install 'psycopg[binary]>=3.1')"
            ) from e

        self.WRITE_POOL_SIZE = write_pool_size
        self.READ_POOL_SIZE = read_pool_size
        self._connect_kwargs = connect_kwargs
        self._max_wait_seconds = float(max_wait_seconds)
        self._closed = False
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._write_conns: List[Any] = []
        self._read_conns: List[Any] = []
        self._write_busy = [False] * self.WRITE_POOL_SIZE
        self._read_busy = [False] * self.READ_POOL_SIZE
        self._write_waiters = 0
        self._read_waiters = 0

        try:
            for _ in range(self.WRITE_POOL_SIZE):
                c = psycopg.connect(**connect_kwargs)
                c.autocommit = False
                self._write_conns.append(c)
            for _ in range(self.READ_POOL_SIZE):
                c = psycopg.connect(**connect_kwargs)
                c.autocommit = False
                self._read_conns.append(c)
        except BaseException:
            self._close_all_unlocked()
            raise

    def snapshot(self) -> Dict[str, Any]:
        """Aggregate lane occupancy for observability."""
        with self._lock:
            w_in = sum(self._write_busy)
            r_in = sum(self._read_busy)
            return {
                "closed": self._closed,
                "write": {
                    "capacity": self.WRITE_POOL_SIZE,
                    "in_use": w_in,
                    "idle": self.WRITE_POOL_SIZE - w_in,
                    "waiters": self._write_waiters,
                },
                "read": {
                    "capacity": self.READ_POOL_SIZE,
                    "in_use": r_in,
                    "idle": self.READ_POOL_SIZE - r_in,
                    "waiters": self._read_waiters,
                },
            }

    def close_all(self) -> None:
        """Close every connection; wake waiters (they will raise if acquire after close)."""
        with self._lock:
            self._close_all_unlocked()

    def _close_all_unlocked(self) -> None:
        """Return close all unlocked."""
        self._closed = True
        for c in self._write_conns + self._read_conns:
            try:
                c.close()
            except Exception:
                pass
        self._write_conns.clear()
        self._read_conns.clear()
        self._write_busy = [False] * self.WRITE_POOL_SIZE
        self._read_busy = [False] * self.READ_POOL_SIZE
        self._cond.notify_all()

    @contextmanager
    def acquire(self, *, write: bool) -> Iterator[Any]:
        """Lease first free connection in the write or read lane."""
        lane = "write" if write else "read"
        pool_size = self.WRITE_POOL_SIZE if write else self.READ_POOL_SIZE
        deadline = time.monotonic() + self._max_wait_seconds
        idx: int | None = None
        conn: Any = None
        wait_started = time.monotonic()
        while True:
            with self._cond:
                if self._closed:
                    raise DriverConnectionError("PostgreSQL connection pool is closed")
                if write:
                    conns = self._write_conns
                    busy = self._write_busy
                else:
                    conns = self._read_conns
                    busy = self._read_busy
                for i in range(len(busy)):
                    if not busy[i]:
                        busy[i] = True
                        idx = i
                        conn = conns[i]
                        break
                if conn is not None:
                    elapsed = time.monotonic() - wait_started
                    if elapsed > 0.001:
                        logger.debug(
                            "Pool acquire(%s) got slot %d in %.3fs",
                            lane,
                            idx,
                            elapsed,
                        )
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DriverOperationError(
                        f"Pool acquire timeout: all {lane} connections busy for "
                        f"{self._max_wait_seconds:g}s"
                    )
                logger.debug(
                    "Pool acquire(%s) waiting — all %d slots busy",
                    lane,
                    pool_size,
                )
                if write:
                    self._write_waiters += 1
                else:
                    self._read_waiters += 1
                try:
                    self._cond.wait(timeout=remaining)
                finally:
                    if write:
                        self._write_waiters -= 1
                    else:
                        self._read_waiters -= 1

        assert idx is not None
        try:
            yield conn
        except BaseException as exc:
            try:
                conn.rollback()
            except Exception as rb:
                raise DriverOperationError(
                    f"Rollback before database retry failed: {rb}"
                ) from rb
            raise exc
        finally:
            with self._cond:
                busy[idx] = False
                self._cond.notify_all()
