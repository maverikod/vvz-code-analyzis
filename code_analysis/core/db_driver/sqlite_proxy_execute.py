"""
Execute database operation via proxy (submit job, poll, delete).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

from ..exceptions import DatabaseOperationError

logger = logging.getLogger(__name__)


def execute_operation_impl(
    ensure_worker_running: Callable[[], None],
    send_request: Callable[[Dict[str, Any]], Dict[str, Any]],
    command_timeout: float,
    poll_interval: float,
    db_path: Any,
    truncate_sql: Callable[[Optional[str], int], Optional[str]],
    operation: str,
    sql: Optional[str] = None,
    params: Optional[Tuple[Any, ...]] = None,
    table_name: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> Any:
    """
    Execute database operation via worker (submit, poll for result, delete job).

    Args:
        ensure_worker_running: Callable that ensures worker is up.
        send_request: Callable(request) -> response dict.
        command_timeout: Max wait for result (seconds).
        poll_interval: Sleep between polls (seconds).
        db_path: Database path for error messages.
        truncate_sql: Callable(sql, max_len) for logging.
        operation: Operation name (execute, fetchone, fetchall, etc.).
        sql: Optional SQL string.
        params: Optional parameters tuple.
        table_name: Optional table name (get_table_info).
        transaction_id: Optional transaction ID.

    Returns:
        Operation result from worker.

    Raises:
        DatabaseOperationError: On submit/poll/delete failure or timeout.
    """
    ensure_worker_running()

    job_id = f"{operation}_{uuid.uuid4().hex[:8]}"
    logger.debug("Executing operation '%s' (job_id=%s)", operation, job_id)

    submit_request: Dict[str, Any] = {
        "command": "submit",
        "job_id": job_id,
        "operation": operation,
    }
    if sql is not None:
        submit_request["sql"] = sql
    if params is not None:
        submit_request["params"] = params
    if table_name is not None:
        submit_request["table_name"] = table_name
    if transaction_id is not None:
        submit_request["transaction_id"] = transaction_id

    try:
        submit_response = send_request(submit_request)
        if not submit_response.get("success"):
            error = submit_response.get("error", "Unknown error")
            raise DatabaseOperationError(
                message=f"Failed to submit job: {error}",
                operation=operation,
                db_path=str(db_path),
                sql=sql,
                params=params,
                timeout=command_timeout,
            )
    except DatabaseOperationError:
        raise
    except Exception as e:
        raise DatabaseOperationError(
            message=f"Failed to submit job: {e}",
            operation=operation,
            db_path=str(db_path),
            sql=sql,
            params=params,
            timeout=command_timeout,
            cause=e,
        ) from e

    max_wait = command_timeout
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            poll_request = {"command": "poll", "job_id": job_id}
            poll_response = send_request(poll_request)

            if not poll_response.get("success"):
                error = poll_response.get("error", "Unknown error")
                raise DatabaseOperationError(
                    message=f"Poll failed: {error}",
                    operation=operation,
                    db_path=str(db_path),
                    sql=sql,
                    params=params,
                    timeout=command_timeout,
                )

            status = poll_response.get("status")
            if status == "pending":
                time.sleep(poll_interval)
                continue
            if status not in ("completed", "failed"):
                raise DatabaseOperationError(
                    message=f"Unknown job status: {status}",
                    operation=operation,
                    db_path=str(db_path),
                    sql=sql,
                    params=params,
                    timeout=command_timeout,
                )

            result = poll_response.get("result")
            error = poll_response.get("error")

            try:
                send_request({"command": "delete", "job_id": job_id})
            except Exception as e:
                logger.warning("Failed to delete job %s: %s", job_id, e)

            if status == "failed" or not poll_response.get("success", False):
                error_msg = (
                    error.get("message", str(error))
                    if isinstance(error, dict)
                    else str(error)
                )
                logger.error(
                    "Database operation '%s' failed: %s",
                    operation,
                    error_msg,
                    extra={
                        "operation": operation,
                        "db_path": str(db_path),
                        "sql": truncate_sql(sql, 200) if sql else None,
                        "params": params,
                    },
                )
                raise DatabaseOperationError(
                    message=f"Database operation failed: {error_msg}",
                    operation=operation,
                    db_path=str(db_path),
                    sql=sql,
                    params=params,
                    timeout=command_timeout,
                )

            logger.debug("Operation '%s' completed successfully", operation)
            if isinstance(result, dict) and "result" in result:
                return result["result"]
            return result

        except DatabaseOperationError:
            raise
        except Exception as e:
            logger.error(
                "Error polling for result: %s",
                e,
                extra={
                    "operation": operation,
                    "db_path": str(db_path),
                    "job_id": job_id,
                },
                exc_info=True,
            )
            raise DatabaseOperationError(
                message=f"Error polling for result: {e}",
                operation=operation,
                db_path=str(db_path),
                sql=sql,
                params=params,
                timeout=command_timeout,
                cause=e,
            ) from e

    logger.error(
        "Database operation '%s' timed out after %ss",
        operation,
        max_wait,
        extra={
            "operation": operation,
            "db_path": str(db_path),
            "sql": truncate_sql(sql, 200) if sql else None,
            "timeout": max_wait,
            "job_id": job_id,
        },
    )
    raise DatabaseOperationError(
        message=f"Database operation '{operation}' timed out after {max_wait}s",
        operation=operation,
        db_path=str(db_path),
        sql=sql,
        params=params,
        timeout=max_wait,
    )
