"""
RPC handlers for schema and transaction operations.

Handles table creation, schema operations, and transactions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from code_analysis.core.database_client.protocol import (
    DataResult,
    ErrorResult,
    SuccessResult,
    ErrorCode,
)
from code_analysis.core.database_driver_pkg.exceptions import TransientDatabaseError
from code_analysis.core.retry_policy import RetryPolicy

from .rpc_handlers_base import parse_logical_write_batches_param

logger = logging.getLogger(__name__)

_LOCK_SCOPE_VALUES = frozenset({"none", "project_write", "project_read"})


def _rpc_write_retry_policy(driver: Any) -> RetryPolicy:
    """Return rpc write retry policy."""
    policy = getattr(driver, "_write_retry_policy", None)
    if policy is not None:
        return policy
    cfg = getattr(driver, "_driver_config", None)
    if isinstance(cfg, dict):
        return RetryPolicy.from_driver_config(cfg)
    return RetryPolicy()


def _rpc_backend_name(driver: Any) -> str:
    """Return rpc backend name."""
    name = type(driver).__name__
    if "PostgreSQL" in name or "postgres" in name.lower():
        return "postgres"
    return name.replace("Driver", "").lower() or "unknown"


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
        """Run multiple execute_batch steps in one transaction (one RPC), with full-tx retry."""
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

        policy = _rpc_write_retry_policy(self.driver)
        backend = _rpc_backend_name(self.driver)
        max_attempts = max(1, policy.attempts)
        logger.info(
            "method=execute_logical_write_operation n_batches=%s lock_scope=%s",
            len(batches),
            lock_scope,
        )

        for attempt_1based in range(1, max_attempts + 1):
            transaction_id: Optional[str] = None
            try:
                transaction_id = self.driver.begin_transaction()
                tid_short = (
                    (transaction_id[:8] + "…")
                    if transaction_id and len(transaction_id) > 8
                    else transaction_id
                )
                logger.debug(
                    "[CHAIN] handler handle_execute_logical_write_operation tid=%s",
                    tid_short,
                )
                if params.get("defer_constraints"):
                    self.driver.execute(
                        "SET CONSTRAINTS ALL DEFERRED", None, transaction_id
                    )
                batch_results: list[dict[str, Any]] = []
                for batch_ops in batches:
                    results = self.driver.execute_batch(batch_ops, transaction_id)
                    batch_results.append({"results": results})
                self.driver.commit_transaction(transaction_id)
                return SuccessResult(
                    data={
                        "batch_results": batch_results,
                        "transaction_id": transaction_id,
                        "metadata": {
                            "operation_name": operation_name,
                            "project_id": project_id,
                            "lock_scope": lock_scope,
                        },
                    }
                )
            except TransientDatabaseError as e:
                if transaction_id is not None:
                    try:
                        self.driver.rollback_transaction(transaction_id)
                    except Exception as rb_err:
                        logger.error(
                            "rollback after logical write failure: %s",
                            rb_err,
                            exc_info=True,
                        )
                        return ErrorResult(
                            error_code=ErrorCode.DATABASE_ERROR,
                            description=f"rollback failed: {rb_err}",
                            details={
                                "retryable": False,
                                "error_kind": "rollback_failed",
                                "message": str(rb_err),
                                "operation_name": operation_name,
                                "attempts": attempt_1based,
                            },
                        )
                if e.commit_outcome_unknown:
                    return ErrorResult(
                        error_code=ErrorCode.DATABASE_ERROR,
                        description=str(e),
                        details=e.to_details(operation_name, attempts=attempt_1based),
                    )
                if not (e.retryable and not e.commit_outcome_unknown):
                    return ErrorResult(
                        error_code=ErrorCode.DATABASE_ERROR,
                        description=str(e),
                        details=e.to_details(operation_name, attempts=attempt_1based),
                    )
                if attempt_1based >= max_attempts:
                    return ErrorResult(
                        error_code=ErrorCode.DATABASE_ERROR,
                        description=str(e),
                        details=e.to_details(operation_name, attempts=max_attempts),
                    )
                logger.info(
                    "[DB_RETRY] backend=%s layer=rpc operation=execute_logical_write_operation "
                    "operation_name=%s attempt=%s/%s sqlstate=%s error_kind=%s",
                    backend,
                    operation_name if operation_name is not None else "none",
                    attempt_1based,
                    max_attempts,
                    e.sqlstate,
                    e.error_kind,
                )
                time.sleep(
                    policy.delay_for_attempt(attempt_1based),
                )
            except Exception as e:
                if transaction_id is not None:
                    try:
                        self.driver.rollback_transaction(transaction_id)
                    except Exception as rb_err:
                        logger.error(
                            "rollback after logical write failure: %s",
                            rb_err,
                            exc_info=True,
                        )
                logger.error(
                    "Error in handle_execute_logical_write_operation: %s",
                    e,
                    exc_info=True,
                )
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=str(e),
                )
