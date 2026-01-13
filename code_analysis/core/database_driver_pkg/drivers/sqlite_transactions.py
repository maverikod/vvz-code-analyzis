"""
SQLite transaction management for SQLite driver.

Handles transaction operations (begin, commit, rollback).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Dict

from ..exceptions import TransactionError


class SQLiteTransactionManager:
    """Manages SQLite transactions."""

    def __init__(self, db_path: Path):
        """Initialize transaction manager.

        Args:
            db_path: Path to database file
        """
        self.db_path = db_path
        self._transactions: Dict[str, sqlite3.Connection] = {}

    def begin_transaction(self) -> str:
        """Begin database transaction.

        Returns:
            Transaction ID (string)

        Raises:
            TransactionError: If transaction cannot be started
        """
        try:
            transaction_id = str(uuid.uuid4())
            # Create separate connection for transaction
            trans_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            trans_conn.row_factory = sqlite3.Row
            trans_conn.execute("PRAGMA foreign_keys = ON")
            trans_conn.execute("BEGIN TRANSACTION")
            self._transactions[transaction_id] = trans_conn
            return transaction_id
        except Exception as e:
            raise TransactionError(f"Failed to begin transaction: {e}") from e

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was committed successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be committed
        """
        if transaction_id not in self._transactions:
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
        """Rollback database transaction.

        Args:
            transaction_id: Transaction ID returned by begin_transaction()

        Returns:
            True if transaction was rolled back successfully, False otherwise

        Raises:
            TransactionError: If transaction cannot be rolled back
        """
        if transaction_id not in self._transactions:
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
        """Close all open transactions."""
        for transaction_id, conn in list(self._transactions.items()):
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            del self._transactions[transaction_id]
