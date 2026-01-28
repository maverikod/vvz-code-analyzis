"""
Base RPC handlers for CRUD operations.

Handles insert, update, delete, select, and execute operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)
from .result import DataResult, ErrorResult, SuccessResult
from .rpc_protocol import ErrorCode

logger = logging.getLogger(__name__)


class _RPCHandlersBaseMixin:
    """Mixin for base CRUD operations."""

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

    def handle_execute(
        self, params: Dict[str, Any]
    ) -> SuccessResult | DataResult | ErrorResult:
        """Handle execute RPC method.

        Args:
            params: Dictionary with 'sql', optional 'params', and optional 'transaction_id' keys

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
            transaction_id = params.get("transaction_id")
            result = self.driver.execute(sql, params_tuple, transaction_id)
            # For execute(), we need to preserve the full result structure
            # including affected_rows, lastrowid, and data (if present)
            # Return as SuccessResult with full result dict to preserve all fields
            return SuccessResult(data=result)
        except Exception as e:
            logger.error(f"Error in handle_execute: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
