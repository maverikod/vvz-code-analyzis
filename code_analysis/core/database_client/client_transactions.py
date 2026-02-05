"""
Transaction methods for client.

Provides transaction management methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class _ClientTransactionsMixin:
    """Mixin class with transaction methods."""

    def begin_transaction(self) -> str:
        """Begin transaction.

        Returns:
            Transaction ID

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        logger.info("[CHAIN] client begin_transaction calling rpc")
        response = self.rpc_client.call("begin_transaction", {})
        result_data = self._extract_result_data(response)
        # _extract_result_data returns {"success": True, "data": {"transaction_id": "..."}}
        # Extract transaction_id from data key
        if isinstance(result_data, dict):
            data = result_data.get("data", {})
            if isinstance(data, dict):
                tid = data.get("transaction_id", "")
                logger.info(
                    "[CHAIN] client begin_transaction returned tid=%s",
                    (tid[:8] + "…") if tid and len(tid) > 8 else tid,
                )
                return tid
        return ""

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if transaction was committed successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        logger.info(
            "[CHAIN] client commit_transaction tid=%s",
            (transaction_id[:8] + "…") if transaction_id else None,
        )
        response = self.rpc_client.call(
            "commit_transaction", {"transaction_id": transaction_id}
        )
        return self._extract_success(response)

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if transaction was rolled back successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        logger.info(
            "[CHAIN] client rollback_transaction tid=%s",
            (transaction_id[:8] + "…") if transaction_id else None,
        )
        response = self.rpc_client.call(
            "rollback_transaction", {"transaction_id": transaction_id}
        )
        return self._extract_success(response)
