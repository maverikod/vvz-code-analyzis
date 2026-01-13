"""
Transaction methods for client.

Provides transaction management methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


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
        response = self.rpc_client.call("begin_transaction", {})
        result_data = self._extract_result_data(response)
        return result_data.get("transaction_id", "")

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
        response = self.rpc_client.call(
            "rollback_transaction", {"transaction_id": transaction_id}
        )
        return self._extract_success(response)
