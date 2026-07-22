"""
RPC handlers for schema and transaction operations.

Handles table creation, schema operations, and transactions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, cast

from code_analysis.core.database.logical_write_program import (
    LogicalWriteProgramV1,
    SqlParamPair,
)
from code_analysis.core.database_client.protocol import (
    DataResult,
    ErrorResult,
    SuccessResult,
    ErrorCode,
)
from code_analysis.core.database_driver_pkg.exceptions import (
    DriverOperationError,
    TransientDatabaseError,
)

from .rpc_handlers_base import parse_logical_write_batches_param

logger = logging.getLogger(__name__)

_LOCK_SCOPE_VALUES = frozenset({"none", "project_write", "project_read"})


class _RPCHandlersSchemaMixin:
    """Mixin for schema and transaction operations. Subclass must set self.driver."""

    driver: Any

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
            logger.debug("[CHAIN] handler handle_begin_transaction calling driver")
            transaction_id = self.driver.begin_transaction()
            logger.debug(
                "[CHAIN] handler handle_begin_transaction returned tid=%s",
                (
                    (transaction_id[:8] + "…")
                    if transaction_id and len(transaction_id) > 8
                    else transaction_id
                ),
            )
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
            logger.debug(
                "[CHAIN] handler handle_commit_transaction tid=%s",
                (
                    (transaction_id[:8] + "…")
                    if len(transaction_id) > 8
                    else transaction_id
                ),
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
            logger.debug(
                "[CHAIN] handler handle_rollback_transaction tid=%s",
                (
                    (transaction_id[:8] + "…")
                    if len(transaction_id) > 8
                    else transaction_id
                ),
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

    def handle_execute_logical_write_operation(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Run multiple execute_batch steps in one transaction (one RPC), with full-tx retry.

        The retry/transaction-orchestration loop now lives on the driver
        (``PostgreSQLDriver.execute_logical_write_operation``, stage-2 driver-prep);
        this handler owns RPC param validation and translates the driver's plain
        return value / raised exceptions back into the ``SuccessResult`` /
        ``ErrorResult`` wire envelope, so current RPC/``DatabaseClient`` callers see
        byte-identical responses.
        """
        err, batches = parse_logical_write_batches_param(params)
        if err is not None:
            return err
        assert batches is not None

        operation_name: str | None = params.get("operation_name")
        if operation_name is not None and not isinstance(operation_name, str):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="operation_name must be a string or null",
            )
        project_id: str | None = params.get("project_id")
        if project_id is not None and not isinstance(project_id, str):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="project_id must be a string or null",
            )
        lock_scope = params.get("lock_scope", "none")
        if not isinstance(lock_scope, str) or lock_scope not in _LOCK_SCOPE_VALUES:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=(
                    "lock_scope must be one of: none, project_write, project_read"
                ),
            )

        program: LogicalWriteProgramV1 = {
            "batches": cast(List[List[SqlParamPair]], batches),
            "lock_scope": lock_scope,  # type: ignore[typeddict-item]
        }
        if params.get("defer_constraints"):
            program["defer_constraints"] = True
        if operation_name is not None:
            program["operation_name"] = operation_name
        if project_id is not None:
            program["project_id"] = project_id

        try:
            data = self.driver.execute_logical_write_operation(program)
        except TransientDatabaseError as e:
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
                details=e.to_details(operation_name),
            )
        except DriverOperationError as e:
            # Rollback-after-transient failure: driver raises DriverOperationError
            # chained from the rollback exception (``raise ... from rb_err``, see
            # PostgreSQLDriver.execute_logical_write_operation docstring). The old
            # handler put the bare rollback exception's own text in
            # details["message"] (not the wrapped "rollback failed: ..." text);
            # __cause__ is that same rollback exception here. The attempt count is
            # attached dynamically (attribute not on the base exception type) so
            # it can be forwarded, matching the old handler's dict key-for-key.
            rollback_cause = e.__cause__
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
                details={
                    "retryable": False,
                    "error_kind": "rollback_failed",
                    "message": str(rollback_cause) if rollback_cause is not None else str(e),
                    "operation_name": operation_name,
                    "attempts": getattr(e, "attempts", None),
                },
            )
        except Exception as e:
            logger.error(
                "Error in handle_execute_logical_write_operation: %s",
                e,
                exc_info=True,
            )
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
        return SuccessResult(data=data)
