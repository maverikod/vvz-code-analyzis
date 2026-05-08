"""
RPC handlers for file trash operations (mark/unmark/hard_delete/get_deleted_files).

FILE_TRASH_SPEC step 12: Expose file trash operations via RPC so that
DatabaseClient and MCP commands can call mark_file_deleted, unmark_file_deleted,
hard_delete_file, get_deleted_files when using the driver process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from code_analysis.core.database_client.protocol import (
    DataResult,
    ErrorCode,
    ErrorResult,
    SuccessResult,
)
from code_analysis.core.database.files.trash_standalone import (
    get_deleted_files_via_driver,
    hard_delete_file_via_driver,
    mark_file_deleted_via_driver,
    unmark_file_deleted_via_driver,
)

logger = logging.getLogger(__name__)


class _RPCHandlersFileTrashMixin:
    """Mixin for file trash RPC: mark_file_deleted, unmark_file_deleted, hard_delete_file, get_deleted_files."""

    def handle_mark_file_deleted(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle mark_file_deleted RPC. Params: file_path, project_id, version_dir?, reason?, trash_dir?."""
        if not isinstance(params, dict):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="mark_file_deleted requires params dict",
            )
        file_path = params.get("file_path")
        project_id = params.get("project_id")
        if not file_path or not project_id:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="mark_file_deleted requires file_path and project_id",
            )
        try:
            version_dir = params.get("version_dir")
            reason = params.get("reason")
            trash_dir = params.get("trash_dir")
            ok = mark_file_deleted_via_driver(
                self.driver,
                file_path=file_path,
                project_id=project_id,
                version_dir=version_dir,
                reason=reason,
                trash_dir=trash_dir,
            )
            return SuccessResult(data={"success": ok})
        except Exception as e:
            logger.error("mark_file_deleted failed: %s", e, exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_unmark_file_deleted(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle unmark_file_deleted RPC. Params: file_path, project_id. Returns success and optional error_code."""
        if not isinstance(params, dict):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="unmark_file_deleted requires params dict",
            )
        file_path = params.get("file_path")
        project_id = params.get("project_id")
        if not file_path or not project_id:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="unmark_file_deleted requires file_path and project_id",
            )
        try:
            out_error: Dict[str, str] = {}
            ok = unmark_file_deleted_via_driver(
                self.driver,
                file_path=file_path,
                project_id=project_id,
                out_error=out_error,
            )
            result: Dict[str, Any] = {"success": ok}
            if out_error:
                result["error_code"] = out_error.get("error_code")
                result["message"] = out_error.get("message")
            return SuccessResult(data=result)
        except Exception as e:
            logger.error("unmark_file_deleted failed: %s", e, exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_hard_delete_file(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle hard_delete_file RPC. Params: file_id."""
        if not isinstance(params, dict):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="hard_delete_file requires params dict",
            )
        file_id = params.get("file_id")
        if file_id is None:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="hard_delete_file requires file_id",
            )
        if not isinstance(file_id, (int, str)):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="hard_delete_file file_id must be a string or integer",
            )
        if isinstance(file_id, str) and not file_id.strip():
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="hard_delete_file file_id must not be empty",
            )
        try:
            hard_delete_file_via_driver(self.driver, file_id)
            return SuccessResult(data={"success": True})
        except Exception as e:
            logger.error("hard_delete_file failed: %s", e, exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_get_deleted_files(
        self, params: Dict[str, Any]
    ) -> DataResult | ErrorResult:
        """Handle get_deleted_files RPC. Params: project_id. Returns list of deleted file rows."""
        if not isinstance(params, dict):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="get_deleted_files requires params dict",
            )
        project_id = params.get("project_id")
        if not project_id:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="get_deleted_files requires project_id",
            )
        try:
            rows = get_deleted_files_via_driver(self.driver, project_id)
            data = [dict(r) for r in rows] if rows else []
            return DataResult(data=data)
        except Exception as e:
            logger.error("get_deleted_files failed: %s", e, exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
