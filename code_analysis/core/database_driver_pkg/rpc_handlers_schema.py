"""
RPC handlers for schema and transaction operations.

Handles table creation, schema operations, and transactions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .result import DataResult, ErrorResult, SuccessResult
from .rpc_protocol import ErrorCode

logger = logging.getLogger(__name__)


class _RPCHandlersSchemaMixin:
    """Mixin for schema and transaction operations."""

    def handle_create_table(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle create_table RPC method.

        Args:
            params: Dictionary with 'schema' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            schema = params.get("schema")
            if not schema:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="schema parameter is required",
                )
            success = self.driver.create_table(schema)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_create_table: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_drop_table(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
        """Handle drop_table RPC method.

        Args:
            params: Dictionary with 'table_name' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            table_name = params.get("table_name")
            if not table_name:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="table_name parameter is required",
                )
            success = self.driver.drop_table(table_name)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_drop_table: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_begin_transaction(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle begin_transaction RPC method.

        Args:
            params: Empty dictionary (no parameters)

        Returns:
            SuccessResult with transaction_id or ErrorResult
        """
        try:
            transaction_id = self.driver.begin_transaction()
            return SuccessResult(data={"transaction_id": transaction_id})
        except Exception as e:
            logger.error(f"Error in handle_begin_transaction: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.TRANSACTION_ERROR,
                description=str(e),
            )

    def handle_commit_transaction(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle commit_transaction RPC method.

        Args:
            params: Dictionary with 'transaction_id' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            transaction_id = params.get("transaction_id")
            if not transaction_id:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="transaction_id parameter is required",
                )
            success = self.driver.commit_transaction(transaction_id)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_commit_transaction: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.TRANSACTION_ERROR,
                description=str(e),
            )

    def handle_rollback_transaction(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle rollback_transaction RPC method.

        Args:
            params: Dictionary with 'transaction_id' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            transaction_id = params.get("transaction_id")
            if not transaction_id:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="transaction_id parameter is required",
                )
            success = self.driver.rollback_transaction(transaction_id)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_rollback_transaction: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.TRANSACTION_ERROR,
                description=str(e),
            )

    def handle_get_table_info(self, params: Dict[str, Any]) -> DataResult | ErrorResult:
        """Handle get_table_info RPC method.

        Args:
            params: Dictionary with 'table_name' key

        Returns:
            DataResult with table info or ErrorResult
        """
        try:
            table_name = params.get("table_name")
            if not table_name:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="table_name parameter is required",
                )
            info = self.driver.get_table_info(table_name)
            return DataResult(data=info)
        except Exception as e:
            logger.error(f"Error in handle_get_table_info: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_sync_schema(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
        """Handle sync_schema RPC method.

        Args:
            params: Dictionary with 'schema_definition' and optional 'backup_dir' keys

        Returns:
            SuccessResult with sync results or ErrorResult
        """
        try:
            schema_definition = params.get("schema_definition")
            if not schema_definition:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="schema_definition parameter is required",
                )
            backup_dir = params.get("backup_dir")
            result = self.driver.sync_schema(schema_definition, backup_dir)
            return SuccessResult(data=result)
        except Exception as e:
            logger.error(f"Error in handle_sync_schema: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.SCHEMA_ERROR,
                description=str(e),
            )
