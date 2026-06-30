"""
PostgreSQL transaction management (separate connection per transaction).

RPC callers that ``begin_transaction`` and pass the returned ``transaction_id`` into
``execute`` / ``execute_batch`` always run on the **dedicated** connection stored in
``PostgreSQLTransactionManager._transactions``. ``PostgreSQLDriver`` must route those
calls to that connection only and **must not** substitute the self-managed write/read
pool (the fixed 3+2 lanes used when ``transaction_id`` is absent, empty, or
``\"local\"``).

While an explicit transaction is open, its connection is **outside** that pool:
additional server connections are held for the lifetime of the transaction. Open
transactions do not occupy the three pooled write slots, but they still consume
PostgreSQL backend resources.

Self-defence: the manager owns the lifecycle of every connection it opens. Each entry
records the monotonic time it was created so ``reap_expired`` can force-close orphans
left behind by a caller that failed to reach commit/rollback. All teardown funnels
through a single idempotent helper, and ``_transactions`` mutations are guarded by a
lock that is never held across a psycopg network call (mirroring the connection pool's
separation of its condition variable from I/O).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from ..exceptions import TransactionError

logger = logging.getLogger(__name__)


def _short_tid(transaction_id: str) -> str:
    """Return a log-friendly short form of a transaction id."""
    if transaction_id and len(transaction_id) > 8:
        return transaction_id[:8] + "…"
    return transaction_id


class _OpenTransaction:
    """One open explicit transaction: its connection plus when it was created."""

    __slots__ = ("conn", "created_monotonic")

    def __init__(self, conn: Any, created_monotonic: float) -> None:
        """Initialize the instance."""
        self.conn = conn
        self.created_monotonic = created_monotonic


class PostgreSQLTransactionManager:
    """One psycopg connection per open RPC transaction.

    Maps each ``transaction_id`` to exactly one connection until commit/rollback.
    This path is orthogonal to ``PostgreSQLConnectionPool``; the driver never
    replaces a transaction-scoped connection with a pooled lease.
    """

    def __init__(
        self,
        connect_kwargs: Dict[str, Any],
        lock_timeout_seconds: float | None = None,
        statement_timeout_seconds: float | None = None,
    ) -> None:
        """Initialize the instance."""
        self._connect_kwargs = connect_kwargs
        self._lock_timeout_seconds = lock_timeout_seconds
        self._statement_timeout_seconds = statement_timeout_seconds
        self._transactions: Dict[str, _OpenTransaction] = {}
        # Guards ``_transactions`` mutations only. Never held across a psycopg
        # network call (connect/commit/rollback/close). Distinct object from the
        # connection pool lock; the two are never nested.
        self._lock = threading.Lock()

    def _apply_set_local_timeouts(self, conn: Any) -> None:
        """Return apply set local timeouts."""
        with conn.cursor() as cur:
            lock = self._lock_timeout_seconds
            if lock is not None and lock > 0:
                ms = int(lock * 1000)
                cur.execute("SET LOCAL lock_timeout = %s", (f"{ms}ms",))
            stmt = self._statement_timeout_seconds
            if stmt is not None and stmt > 0:
                ms = int(stmt * 1000)
                cur.execute("SET LOCAL statement_timeout = %s", (f"{ms}ms",))

    def _pop_locked(self, transaction_id: str) -> Optional[_OpenTransaction]:
        """Atomically remove and return the record for ``transaction_id`` (or None)."""
        with self._lock:
            return self._transactions.pop(transaction_id, None)

    def _teardown_conn(self, conn: Any, *, reason: str, tid: str = "") -> None:
        """Roll back then close a connection, swallowing per-step errors.

        Cleanup of a transaction connection lives in exactly this place. Both
        steps are best-effort: a failure is logged at WARNING and does not
        propagate, so callers can always treat the connection as released.
        """
        try:
            conn.rollback()
        except Exception as e:
            logger.warning(
                "[CHAIN] postgres_transactions teardown rollback failed "
                "reason=%s tid=%s: %s",
                reason,
                tid,
                e,
            )
        try:
            conn.close()
        except Exception as e:
            logger.warning(
                "[CHAIN] postgres_transactions teardown close failed "
                "reason=%s tid=%s: %s",
                reason,
                tid,
                e,
            )

    def get_connection(self, transaction_id: str) -> Any:
        """Return the connection for an open transaction, or ``None`` if unknown.

        Lets the driver route ``execute`` / ``execute_batch`` to the dedicated
        connection without reaching into ``_transactions`` directly.
        """
        with self._lock:
            record = self._transactions.get(transaction_id)
            return record.conn if record is not None else None

    def begin_transaction(self) -> str:
        """Return begin transaction."""
        try:
            import psycopg
        except ImportError as e:
            raise TransactionError(
                "psycopg is required for PostgreSQL driver. "
                "Install with: pip install 'psycopg[binary]>=3.1' or pip install -e ."
            ) from e

        transaction_id = str(uuid.uuid4())
        logger.debug(
            "[CHAIN] postgres_transactions begin_transaction tid=%s",
            _short_tid(transaction_id),
        )
        try:
            conn = psycopg.connect(**self._connect_kwargs)
            conn.autocommit = False
            try:
                self._apply_set_local_timeouts(conn)
            except Exception as e:
                self._teardown_conn(
                    conn, reason="begin_set_timeouts_failed", tid=_short_tid(transaction_id)
                )
                raise TransactionError(
                    f"Failed to set transaction timeouts: {e}"
                ) from e
            with self._lock:
                self._transactions[transaction_id] = _OpenTransaction(
                    conn, time.monotonic()
                )
            return transaction_id
        except TransactionError:
            raise
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction: {e}") from e

    def close_transaction(self, transaction_id: str, *, reason: str) -> bool:
        """Idempotently roll back and close an open transaction.

        Returns ``True`` if an open transaction was found and torn down, ``False``
        if there was nothing to do. Calling it twice for the same id is safe: the
        second call simply returns ``False`` without raising.
        """
        record = self._pop_locked(transaction_id)
        if record is None:
            return False
        self._teardown_conn(
            record.conn, reason=reason, tid=_short_tid(transaction_id)
        )
        return True

    def commit_transaction(self, transaction_id: str) -> bool:
        """Return commit transaction."""
        logger.debug(
            "[CHAIN] postgres_transactions commit_transaction tid=%s n_open=%s",
            _short_tid(transaction_id),
            len(self._transactions),
        )
        record = self._pop_locked(transaction_id)
        if record is None:
            logger.warning(
                "[CHAIN] postgres_transactions commit_transaction tid not found"
            )
            raise TransactionError(f"Transaction {transaction_id} not found")

        conn = record.conn
        try:
            conn.commit()
        except Exception as e:
            # The entry is already removed; make sure the backend connection is
            # not leaked even though the commit failed.
            self._teardown_conn(
                conn, reason="commit_failed", tid=_short_tid(transaction_id)
            )
            raise TransactionError(f"Failed to commit transaction: {e}") from e
        self._teardown_conn(conn, reason="committed", tid=_short_tid(transaction_id))
        return True

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Return rollback transaction."""
        logger.debug(
            "[CHAIN] postgres_transactions rollback_transaction tid=%s n_open=%s",
            _short_tid(transaction_id),
            len(self._transactions),
        )
        record = self._pop_locked(transaction_id)
        if record is None:
            logger.warning(
                "[CHAIN] postgres_transactions rollback_transaction tid not found"
            )
            raise TransactionError(f"Transaction {transaction_id} not found")

        self._teardown_conn(
            record.conn, reason="rolled_back", tid=_short_tid(transaction_id)
        )
        return True

    def reap_expired(self, max_age_seconds: float) -> int:
        """Force-close every open transaction older than ``max_age_seconds``.

        Safe to call concurrently with begin/commit/rollback: it iterates over a
        snapshot and re-checks membership (via the atomic pop) before closing, so
        a transaction committed in the meantime is not double-closed.

        Returns the number of transactions reaped.
        """
        now = time.monotonic()
        reaped = 0
        for transaction_id, record in list(self._transactions.items()):
            if now - record.created_monotonic <= max_age_seconds:
                continue
            popped = self._pop_locked(transaction_id)
            if popped is None:
                # Already committed/rolled back/reaped by another thread.
                continue
            self._teardown_conn(
                popped.conn,
                reason="reaped_expired",
                tid=_short_tid(transaction_id),
            )
            reaped += 1
        return reaped

    def close_all(self) -> None:
        """Return close all."""
        with self._lock:
            records = list(self._transactions.items())
            self._transactions.clear()
        for transaction_id, record in records:
            self._teardown_conn(
                record.conn, reason="close_all", tid=_short_tid(transaction_id)
            )
