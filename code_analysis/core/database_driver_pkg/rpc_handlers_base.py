"""
Base RPC handlers for CRUD operations.

Handles insert, update, delete, select, and execute operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from code_analysis.core.database_client.protocol import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
    DataResult,
    ErrorResult,
    SuccessResult,
    ErrorCode,
)

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
            raw_params = params.get("params")
            if raw_params is None:
                params_tuple = None
            elif isinstance(raw_params, (list, tuple)):
                params_tuple = tuple(raw_params) if raw_params else ()
            elif isinstance(raw_params, dict):
                params_tuple = raw_params
            else:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"'params' must be list, tuple, dict, or null; got {type(raw_params).__name__}",
                )
            transaction_id = params.get("transaction_id")
            sql_preview = (
                (sql.strip()[:60] + "…") if len(sql.strip()) > 60 else sql.strip()
            )
            logger.info(
                "[CHAIN] handler handle_execute sql_preview=%s tid=%s",
                sql_preview,
                (transaction_id[:8] + "…") if transaction_id else None,
            )
            result = self.driver.execute(sql, params_tuple, transaction_id)
            # Log SELECT result size for diagnostics (e.g. non-vectorized chunks query)
            if isinstance(result, dict) and "data" in result:
                data_val = result["data"]
                if isinstance(data_val, list):
                    logger.info(
                        "[CHAIN] handle_execute SELECT n_rows=%s",
                        len(data_val),
                    )
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

    def handle_execute_batch(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle execute_batch RPC: run multiple SQL statements in one round-trip.

        Args:
            params: Dict with 'operations' (list of {sql, params}) and optional 'transaction_id'.

        Returns:
            SuccessResult with data.results = list of result dicts, or ErrorResult.
        """
        try:
            operations_raw = params.get("operations")
            if not isinstance(operations_raw, list):
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="operations (list) is required",
                )
            operations: list = []
            for item in operations_raw:
                if not isinstance(item, dict):
                    return ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description="Each operation must be {sql, params}",
                    )
                sql = item.get("sql")
                if not sql:
                    return ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description="Each operation must have 'sql'",
                    )
                p = item.get("params")
                if p is None:
                    bind_params = None
                elif isinstance(p, (list, tuple)):
                    bind_params = tuple(p)
                else:
                    return ErrorResult(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        description=f"Each operation 'params' must be list, tuple, or null; got {type(p).__name__}",
                    )
                operations.append((sql, bind_params))
            transaction_id = params.get("transaction_id")
            logger.info(
                "[CHAIN] handler handle_execute_batch n_ops=%s tid=%s",
                len(operations),
                (transaction_id[:8] + "…") if transaction_id else None,
            )
            results = self.driver.execute_batch(operations, transaction_id)
            return SuccessResult(data={"results": results})
        except Exception as e:
            logger.error(f"Error in handle_execute_batch: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
