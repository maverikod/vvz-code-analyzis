"""
Shared RPC request dispatch for database driver (socket server and in-process client).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging

from code_analysis.core.database_client.protocol import (
    BaseResult,
    DataResult,
    DeleteRequest,
    ErrorCode,
    ErrorResult,
    InsertRequest,
    RPCError,
    RPCRequest,
    RPCResponse,
    SelectRequest,
    SuccessResult,
    UpdateRequest,
)

from .rpc_handlers import RPCHandlers

logger = logging.getLogger(__name__)


def process_rpc_request(handlers: RPCHandlers, request: RPCRequest) -> RPCResponse:
    """Route a single RPC request through handlers and build RPCResponse.

    Same semantics as ``RPCServer._process_request`` (used by the Unix-socket
    server and by :class:`~code_analysis.core.database_client.in_process_rpc_client.InProcessRpcClient`).
    """
    method = request.method
    params = request.params if isinstance(request.params, dict) else {}
    tid = params.get("transaction_id")
    logger.info(
        "[CHAIN] rpc_dispatch process_rpc_request method=%s tid=%s",
        method,
        (str(tid)[:8] + "…") if tid and len(str(tid)) > 8 else tid,
    )

    result: SuccessResult | DataResult | ErrorResult

    try:
        if method == "insert":
            try:
                insert_request = InsertRequest.from_dict(params)
                result = handlers.handle_insert(insert_request)
            except Exception as e:
                logger.error(f"Error creating InsertRequest: {e}", exc_info=True)
                result = ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Invalid insert request: {e}",
                )
        elif method == "update":
            try:
                update_request = UpdateRequest.from_dict(params)
                result = handlers.handle_update(update_request)
            except Exception as e:
                logger.error(f"Error creating UpdateRequest: {e}", exc_info=True)
                result = ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Invalid update request: {e}",
                )
        elif method == "delete":
            try:
                delete_request = DeleteRequest.from_dict(params)
                result = handlers.handle_delete(delete_request)
            except Exception as e:
                logger.error(f"Error creating DeleteRequest: {e}", exc_info=True)
                result = ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Invalid delete request: {e}",
                )
        elif method == "select":
            try:
                select_request = SelectRequest.from_dict(params)
                result = handlers.handle_select(select_request)
            except Exception as e:
                logger.error(f"Error creating SelectRequest: {e}", exc_info=True)
                result = ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Invalid select request: {e}",
                )
        else:
            handler_map = {
                "create_table": handlers.handle_create_table,
                "drop_table": handlers.handle_drop_table,
                "execute": handlers.handle_execute,
                "execute_batch": handlers.handle_execute_batch,
                "execute_logical_write_operation": (
                    handlers.handle_execute_logical_write_operation
                ),
                "begin_transaction": handlers.handle_begin_transaction,
                "commit_transaction": handlers.handle_commit_transaction,
                "rollback_transaction": handlers.handle_rollback_transaction,
                "get_table_info": handlers.handle_get_table_info,
                "sync_schema": handlers.handle_sync_schema,
                "query_ast": handlers.handle_query_ast,
                "query_cst": handlers.handle_query_cst,
                "modify_ast": handlers.handle_modify_ast,
                "modify_cst": handlers.handle_modify_cst,
                "index_file": handlers.handle_index_file,
                "mark_file_deleted": handlers.handle_mark_file_deleted,
                "unmark_file_deleted": handlers.handle_unmark_file_deleted,
                "hard_delete_file": handlers.handle_hard_delete_file,
                "get_deleted_files": handlers.handle_get_deleted_files,
                "qa_set_db_retry_injections": handlers.handle_qa_set_db_retry_injections,
            }

            handler = handler_map.get(method)
            if not handler:
                return RPCResponse(
                    error=RPCError(
                        code=ErrorCode.INVALID_REQUEST,
                        message=f"Unknown method: {method}",
                    ),
                    request_id=request.request_id,
                )

            result = handler(params)

        if isinstance(result, BaseResult):
            if result.is_error() and isinstance(result, ErrorResult):
                rpc_error = result.to_rpc_error()
                logger.warning(
                    "[CHAIN] rpc_dispatch process_rpc_request method=%s handler_error=%s",
                    method,
                    getattr(rpc_error, "message", rpc_error),
                )
                return RPCResponse(
                    error=rpc_error,
                    request_id=request.request_id,
                )
            result_dict = result.to_dict()
            return RPCResponse(result=result_dict, request_id=request.request_id)

        logger.error(f"Unexpected result type: {type(result)}")
        return RPCResponse(
            error=RPCError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unexpected result type from handler",
            ),
            request_id=request.request_id,
        )
    except Exception as e:
        logger.error(
            "[CHAIN] rpc_dispatch process_rpc_request method=%s exception: %s",
            method,
            e,
            exc_info=True,
        )
        return RPCResponse(
            error=RPCError(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
            ),
            request_id=request.request_id,
        )
