"""
PostgreSQL transaction management (separate connection per transaction).

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
    """One psycopg connection per open transaction (same contract as SQLite driver)."""

    def __init__(self, connect_kwargs: Dict[str, Any]) -> None:
        self._connect_kwargs = connect_kwargs
        self._transactions: Dict[str, Any] = {}

    def begin_transaction(self) -> str:
        try:
            import psycopg  # type: ignore[import-untyped]
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
            self._transactions[transaction_id] = conn
            return transaction_id
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
