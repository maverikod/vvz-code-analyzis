"""
Thread-safe PostgreSQL connection pool: 3 write + 2 read lanes (first-free).

Used only for **self-managed** driver work (no external ``transaction_id``, or
``transaction_id=\"local\"``). Explicit RPC transactions use separate connections
via ``PostgreSQLTransactionManager`` and do not lease from this pool.

**Contention:** if all three write connections are busy with long-running
self-managed writes, ``acquire(write=True)`` waits up to ``max_wait_seconds`` (default
30s) for a slot, then raises ``DriverOperationError``. The two read connections
are independent; read traffic can proceed while writes are saturated, subject to DB
locks and SQL semantics.

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
    """Exactly five connections: three write, two read; first idle slot per lane."""

    WRITE_POOL_SIZE = 3
    READ_POOL_SIZE = 2

    def __init__(
        self,
        connect_kwargs: Dict[str, Any],
        *,
        max_wait_seconds: float = 30.0,
    ) -> None:
        try:
            import psycopg
        except ImportError as e:
            raise DriverConnectionError(
                "PostgreSQL pool requires psycopg (pip install 'psycopg[binary]>=3.1')"
            ) from e

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
