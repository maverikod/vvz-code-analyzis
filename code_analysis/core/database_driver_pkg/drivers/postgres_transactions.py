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

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

from ..exceptions import TransactionError

logger = logging.getLogger(__name__)


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
        self._connect_kwargs = connect_kwargs
        self._lock_timeout_seconds = lock_timeout_seconds
        self._statement_timeout_seconds = statement_timeout_seconds
        self._transactions: Dict[str, Any] = {}

    def _apply_set_local_timeouts(self, conn: Any) -> None:
        with conn.cursor() as cur:
            lock = self._lock_timeout_seconds
            if lock is not None and lock > 0:
                ms = int(lock * 1000)
                cur.execute("SET LOCAL lock_timeout = %s", (f"{ms}ms",))
            stmt = self._statement_timeout_seconds
            if stmt is not None and stmt > 0:
                ms = int(stmt * 1000)
                cur.execute("SET LOCAL statement_timeout = %s", (f"{ms}ms",))

    def begin_transaction(self) -> str:
        try:
            import psycopg
        except ImportError as e:
            raise TransactionError(
                "psycopg is required for PostgreSQL driver. "
                "Install with: pip install 'psycopg[binary]>=3.1' or pip install -e ."
            ) from e

        transaction_id = str(uuid.uuid4())
        logger.info(
            "[CHAIN] postgres_transactions begin_transaction tid=%s",
            transaction_id[:8] + "…",
        )
        try:
            conn = psycopg.connect(**self._connect_kwargs)
            conn.autocommit = False
            try:
                self._apply_set_local_timeouts(conn)
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass
                raise TransactionError(
                    f"Failed to set transaction timeouts: {e}"
                ) from e
            self._transactions[transaction_id] = conn
            return transaction_id
        except TransactionError:
            raise
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction: {e}") from e

    def commit_transaction(self, transaction_id: str) -> bool:
        logger.info(
            "[CHAIN] postgres_transactions commit_transaction tid=%s n_open=%s",
            (transaction_id[:8] + "…") if len(transaction_id) > 8 else transaction_id,
            len(self._transactions),
        )
        if transaction_id not in self._transactions:
            logger.warning(
                "[CHAIN] postgres_transactions commit_transaction tid not found"
            )
            raise TransactionError(f"Transaction {transaction_id} not found")

        try:
            conn = self._transactions[transaction_id]
            conn.commit()
            conn.close()
            del self._transactions[transaction_id]
            return True
        except Exception as e:
            raise TransactionError(f"Failed to commit transaction: {e}") from e

    def rollback_transaction(self, transaction_id: str) -> bool:
        logger.info(
            "[CHAIN] postgres_transactions rollback_transaction tid=%s n_open=%s",
            (transaction_id[:8] + "…") if len(transaction_id) > 8 else transaction_id,
            len(self._transactions),
        )
        if transaction_id not in self._transactions:
            logger.warning(
                "[CHAIN] postgres_transactions rollback_transaction tid not found"
            )
            raise TransactionError(f"Transaction {transaction_id} not found")

        try:
            conn = self._transactions[transaction_id]
            conn.rollback()
            conn.close()
            del self._transactions[transaction_id]
            return True
        except Exception as e:
            raise TransactionError(f"Failed to rollback transaction: {e}") from e

    def close_all(self) -> None:
        for transaction_id, conn in list(self._transactions.items()):
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            del self._transactions[transaction_id]
