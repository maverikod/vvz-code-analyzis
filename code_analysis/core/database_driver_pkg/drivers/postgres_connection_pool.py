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

**LAZY connection establishment (regression fix, bug 8e6acb34 follow-up).**
``__init__`` does NOT open any connections -- it only allocates ``None``
placeholder slots. A slot's real ``psycopg.connect()`` happens on that
slot's first ``acquire()``, performed OUTSIDE the lock, and the resulting
connection is cached in the slot for the pool's remaining lifetime (later
acquires of the same slot reuse it, no reconnect). This makes construction
O(1) regardless of lane size, which is what makes a 12-slot read lane
affordable: raising ``read_pool_size`` from 2 to 12 (the bug 8e6acb34 fix)
used to add 10 more synchronous ``psycopg.connect()`` round-trips to EVERY
fresh pool construction (~1.5-2s observed) -- a real per-``DatabaseClient``-open
latency regression, not just a test-timing artifact, since
``BaseMCPCommand._open_database_from_config()`` opens a fresh client (and
therefore a fresh pool) on demand.

Locking design: claiming a free slot index (``busy[idx] = True``) under
``self._cond`` is itself the sole mutual-exclusion mechanism for lazy
connect -- once claimed, no other thread can see that slot as free until
this thread releases it in ``acquire()``'s ``finally``, so at most one
thread ever attempts to establish a given slot's connection at a time, and
two threads can never race to create two connections for the same slot. The
``psycopg.connect()`` call itself runs OUTSIDE the lock (after claiming,
before yielding), so one slow or hanging connect never blocks other threads
that are acquiring different slots (already-established or independently
establishing) -- unlike holding ``self._cond`` across the network call,
which would serialize every waiter behind one connect regardless of lane
size. If the lazy connect raises, the slot is released back as unestablished
(``busy[idx] = False``, connection stays ``None``) before the error
propagates as ``DriverConnectionError``, so a later ``acquire()`` can retry
that same slot from scratch instead of it being stuck busy or half-open.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from ..exceptions import DriverConnectionError, DriverOperationError

logger = logging.getLogger(__name__)


class PostgreSQLConnectionPool:
    """Configurable write/read lanes (default 3 write, 2 read); first idle slot per lane.

    Connections are established LAZILY -- see the module docstring's "LAZY
    connection establishment" section for the locking design.
    """

    def __init__(
        self,
        connect_kwargs: Dict[str, Any],
        *,
        max_wait_seconds: float = 30.0,
        write_pool_size: int = 3,
        read_pool_size: int = 2,
    ) -> None:
        """Initialize the instance.

        Does NOT open any connections -- lane slots start unestablished
        (``None``) and connect lazily on first ``acquire()`` of that slot
        (see module docstring). Construction is therefore O(1) and cheap
        regardless of lane size.

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

        self._psycopg = psycopg
        self.WRITE_POOL_SIZE = write_pool_size
        self.READ_POOL_SIZE = read_pool_size
        self._connect_kwargs = connect_kwargs
        self._max_wait_seconds = float(max_wait_seconds)
        self._closed = False
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        # None = slot not yet established; set on that slot's first acquire()
        # and reused for the pool's remaining lifetime thereafter.
        self._write_conns: List[Optional[Any]] = [None] * self.WRITE_POOL_SIZE
        self._read_conns: List[Optional[Any]] = [None] * self.READ_POOL_SIZE
        self._write_busy = [False] * self.WRITE_POOL_SIZE
        self._read_busy = [False] * self.READ_POOL_SIZE
        self._write_waiters = 0
        self._read_waiters = 0

    def snapshot(self) -> Dict[str, Any]:
        """Aggregate lane occupancy for observability (established vs not-yet-established)."""
        with self._lock:
            w_in = sum(self._write_busy)
            r_in = sum(self._read_busy)
            w_established = sum(1 for c in self._write_conns if c is not None)
            r_established = sum(1 for c in self._read_conns if c is not None)
            return {
                "closed": self._closed,
                "write": {
                    "capacity": self.WRITE_POOL_SIZE,
                    "in_use": w_in,
                    "idle": self.WRITE_POOL_SIZE - w_in,
                    "waiters": self._write_waiters,
                    "established": w_established,
                },
                "read": {
                    "capacity": self.READ_POOL_SIZE,
                    "in_use": r_in,
                    "idle": self.READ_POOL_SIZE - r_in,
                    "waiters": self._read_waiters,
                    "established": r_established,
                },
            }

    def close_all(self) -> None:
        """Close every established connection; wake waiters (they will raise if acquire after close)."""
        with self._lock:
            self._close_all_unlocked()

    def _close_all_unlocked(self) -> None:
        """Return close all unlocked."""
        self._closed = True
        for c in self._write_conns + self._read_conns:
            if c is None:
                continue
            try:
                c.close()
            except Exception:
                pass
        self._write_conns = [None] * self.WRITE_POOL_SIZE
        self._read_conns = [None] * self.READ_POOL_SIZE
        self._write_busy = [False] * self.WRITE_POOL_SIZE
        self._read_busy = [False] * self.READ_POOL_SIZE
        self._cond.notify_all()

    def _establish_slot(self, lane: str, conns: List[Optional[Any]], idx: int) -> Any:
        """Lazily connect slot ``idx`` if unestablished; return its connection.

        Called with ``busy[idx]`` already claimed True (by ``acquire()``,
        under the lock) and the lock itself NOT held -- claiming the slot is
        what prevents two threads from racing to establish it (see module
        docstring). On failure the caller is responsible for releasing the
        slot back; this method never mutates ``busy``.
        """
        conn = conns[idx]
        if conn is not None:
            return conn
        try:
            conn = self._psycopg.connect(**self._connect_kwargs)
            conn.autocommit = False
        except BaseException as exc:
            raise DriverConnectionError(
                f"Failed to lazily establish PostgreSQL {lane} pool connection "
                f"(slot {idx}): {exc}"
            ) from exc
        return conn

    @contextmanager
    def acquire(self, *, write: bool) -> Iterator[Any]:
        """Lease first free connection in the write or read lane.

        Lazily establishes the slot's connection on its first lease (see
        module docstring "LAZY connection establishment").
        """
        lane = "write" if write else "read"
        pool_size = self.WRITE_POOL_SIZE if write else self.READ_POOL_SIZE
        deadline = time.monotonic() + self._max_wait_seconds
        idx: int | None = None
        wait_started = time.monotonic()
        while True:
            with self._cond:
                if self._closed:
                    raise DriverConnectionError("PostgreSQL connection pool is closed")
                conns = self._write_conns if write else self._read_conns
                busy = self._write_busy if write else self._read_busy
                for i in range(len(busy)):
                    if not busy[i]:
                        busy[i] = True
                        idx = i
                        break
                if idx is not None:
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
        # Slot `idx` is claimed (busy[idx] == True) by this thread alone from
        # here on -- establish/reuse its connection OUTSIDE the lock so a
        # slow/hanging connect cannot block other threads acquiring other
        # slots. On failure, release the slot back as unestablished so a
        # later acquire can retry it, then propagate.
        try:
            conn = self._establish_slot(lane, conns, idx)
        except BaseException:
            with self._cond:
                busy[idx] = False
                self._cond.notify_all()
            raise

        with self._cond:
            if self._closed:
                # close_all() ran while we were connecting outside the lock;
                # don't leak the fresh connection into a closed pool.
                busy[idx] = False
                self._cond.notify_all()
                try:
                    conn.close()
                except Exception:
                    pass
                raise DriverConnectionError("PostgreSQL connection pool is closed")
            conns[idx] = conn

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
