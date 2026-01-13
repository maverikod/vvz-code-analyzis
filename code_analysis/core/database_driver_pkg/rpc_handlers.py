"""
RPC method handlers for database driver operations.

Handles individual RPC method calls by delegating to driver.
Uses BaseRequest and BaseResult classes for type safety and validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .drivers.base import BaseDatabaseDriver
from .exceptions import DriverOperationError
from .request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)
from .result import DataResult, ErrorResult, SuccessResult
from .rpc_protocol import ErrorCode

logger = logging.getLogger(__name__)


class RPCHandlers:
    """RPC method handlers for database operations.

    All handlers use BaseRequest and BaseResult classes for type safety
    and proper validation.
    """

    def __init__(self, driver: BaseDatabaseDriver):
        """Initialize RPC handlers.

        Args:
            driver: Database driver instance
        """
        self.driver = driver

    def handle_create_table(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
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

    def handle_insert(self, request: InsertRequest) -> SuccessResult | ErrorResult:
        """Handle insert RPC method using InsertRequest.

        Args:
            request: InsertRequest instance

        Returns:
            SuccessResult with row_id or ErrorResult
        """
        try:
            request.validate()
            row_id = self.driver.insert(request.table_name, request.data)
            return SuccessResult(data={"row_id": row_id})
        except ValueError as e:
            logger.error(f"Validation error in handle_insert: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_insert: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_update(self, request: UpdateRequest) -> SuccessResult | ErrorResult:
        """Handle update RPC method using UpdateRequest.

        Args:
            request: UpdateRequest instance

        Returns:
            SuccessResult with affected_rows or ErrorResult
        """
        try:
            request.validate()
            affected_rows = self.driver.update(
                request.table_name, request.where, request.data
            )
            return SuccessResult(data={"affected_rows": affected_rows})
        except ValueError as e:
            logger.error(f"Validation error in handle_update: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_update: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_delete(self, request: DeleteRequest) -> SuccessResult | ErrorResult:
        """Handle delete RPC method using DeleteRequest.

        Args:
            request: DeleteRequest instance

        Returns:
            SuccessResult with affected_rows or ErrorResult
        """
        try:
            request.validate()
            affected_rows = self.driver.delete(request.table_name, request.where)
            return SuccessResult(data={"affected_rows": affected_rows})
        except ValueError as e:
            logger.error(f"Validation error in handle_delete: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_delete: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_select(self, request: SelectRequest) -> DataResult | ErrorResult:
        """Handle select RPC method using SelectRequest.

        Args:
            request: SelectRequest instance

        Returns:
            DataResult with rows or ErrorResult
        """
        try:
            request.validate()
            rows = self.driver.select(
                table_name=request.table_name,
                where=request.where,
                columns=request.columns,
                limit=request.limit,
                offset=request.offset,
                order_by=request.order_by,
            )
            return DataResult(data=rows)
        except ValueError as e:
            logger.error(f"Validation error in handle_select: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_select: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_execute(self, params: Dict[str, Any]) -> SuccessResult | DataResult | ErrorResult:
        """Handle execute RPC method.

        Args:
            params: Dictionary with 'sql' and optional 'params' keys

        Returns:
            SuccessResult, DataResult, or ErrorResult
        """
        try:
            sql = params.get("sql")
            if not sql:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="sql parameter is required",
                )
            params_tuple = params.get("params")
            result = self.driver.execute(sql, params_tuple)
            # If result contains data, return DataResult, otherwise SuccessResult
            if "data" in result:
                return DataResult(data=result["data"])
            return SuccessResult(data=result)
        except Exception as e:
            logger.error(f"Error in handle_execute: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_begin_transaction(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
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

    def handle_commit_transaction(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
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

    def handle_rollback_transaction(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
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
