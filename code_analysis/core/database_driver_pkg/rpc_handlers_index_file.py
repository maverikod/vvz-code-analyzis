"""
RPC handler for index_file: full file index (AST, CST, entities, code_content) in driver process.

Exposes "index_file" RPC used by the indexing worker. Reuses CodeDatabase.update_file_data;
clears needs_chunking after success (single flag for indexer and vectorization).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from code_analysis.core.database_client.protocol import (
    ErrorResult,
    SuccessResult,
    ErrorCode,
)

logger = logging.getLogger(__name__)


class _RPCHandlersIndexFileMixin:
    """Mixin for index_file RPC: run full file index in driver process and clear needs_chunking."""

    def handle_index_file(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
        """Handle index_file RPC: index one file (AST, CST, entities, code_content) and clear needs_chunking.

        Params: file_path (str, absolute), project_id (str).
        Project root is read from projects.root_path in the DB.
        On success, sets needs_chunking = 0 for the file so vectorization can still pick it via code_chunks.

        Args:
            params: Dict with file_path, project_id

        Returns:
            SuccessResult with update result dict, or ErrorResult on failure
        """
        file_path = params.get("file_path") if isinstance(params, dict) else None
        project_id = params.get("project_id") if isinstance(params, dict) else None
        if not file_path or not project_id:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="index_file requires file_path and project_id",
            )
        if not hasattr(self.driver, "db_path") or not self.driver.db_path:
            return ErrorResult(
                error_code=ErrorCode.INTERNAL_ERROR,
                description="Driver has no db_path (index_file only supported for SQLite driver)",
            )
        logger.info(
            "[index_file] Starting: file_path=%s project_id=%s",
            file_path,
            project_id,
        )
        try:
            # Resolve project root from DB
            exec_result = self.driver.execute(
                "SELECT root_path FROM projects WHERE id = ?",
                (project_id,),
                None,
            )
            data = exec_result.get("data") if isinstance(exec_result, dict) else None
            if not data or len(data) == 0:
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Project not found: {project_id}",
                )
            root_path = data[0].get("root_path")
            if not root_path:
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Project has no root_path: {project_id}",
                )

            # Reuse existing driver connection: do NOT create a second CodeDatabase(driver_config)
            # (that would open a second connection and call sync_schema(), causing lock contention
            # and "Schema synchronization failed: disk I/O error"). Use from_existing_driver so
            # only one connection touches the DB in this process.
            from code_analysis.core.database import CodeDatabase

            logger.debug(
                "[index_file] Using from_existing_driver (single connection, no sync_schema)"
            )
            db = CodeDatabase.from_existing_driver(self.driver)
            update_result = db.update_file_data(
                file_path, project_id, Path(root_path)
            )
            # Do not disconnect db.driver: it is the RPC server's shared connection.

            if not update_result.get("success"):
                error_msg = update_result.get("error", "Unknown error")
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=error_msg,
                )

            # Clear needs_chunking after success (A.3) so indexer and vectorization share one flag
            abs_path = update_result.get("file_path", file_path)
            try:
                self.driver.execute(
                    "UPDATE files SET needs_chunking = 0 WHERE path = ? AND project_id = ?",
                    (abs_path, project_id),
                    None,
                )
            except Exception as e:
                logger.warning(
                    "Failed to clear needs_chunking after index_file for %s: %s",
                    abs_path,
                    e,
                )
                # Still return success; index completed

            logger.info(
                "[index_file] Completed: file_path=%s success=True",
                update_result.get("file_path", file_path),
            )
            return SuccessResult(data=update_result)
        except Exception as e:
            logger.error("index_file failed for %s: %s", file_path, e, exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
