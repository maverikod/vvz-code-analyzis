"""
RPC handler for index_file: full file index (AST, CST, entities, code_content) in driver process.

Exposes "index_file" RPC used by the indexing worker. Delegates to
:func:`~code_analysis.core.database.files.update_standalone.update_file_data_via_driver`;
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


def _is_fk_or_integrity_error(exc: BaseException) -> bool:
    """Return True if exception is FK or integrity constraint (project-deleted race)."""
    try:
        import psycopg

        if isinstance(
            exc,
            (
                psycopg.errors.ForeignKeyViolation,
                psycopg.errors.UniqueViolation,
                psycopg.errors.NotNullViolation,
            ),
        ):
            return True
    except ImportError:
        pass
    msg = (getattr(exc, "args", (None,))[0] or str(exc)).lower()
    return "foreign key" in msg or "integrity" in msg


class _RPCHandlersIndexFileMixin:
    """Mixin for index_file RPC: run full file index in driver process and clear needs_chunking."""

    driver: Any

    def handle_index_file(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
        """Handle index_file RPC: index one file (AST, CST, entities, code_content) and clear needs_chunking.

        Params: file_path (str, project-relative or absolute), project_id (str).
        Project root is resolved via watch_dir_paths + projects.name (canonical 3-component scheme):
        watch_dir_paths.absolute_path / projects.name / files.relative_path.
        On success, sets needs_chunking = 0 so vectorization can pick the file via code_chunks.

        Args:
            params: Dict with file_path, project_id.

        Returns:
            SuccessResult with update result dict, or ErrorResult on failure.
        """
        file_path = params.get("file_path") if isinstance(params, dict) else None
        project_id = params.get("project_id") if isinstance(params, dict) else None
        if not file_path or not project_id:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="index_file requires file_path and project_id",
            )
        logger.debug(
            "[index_file] Starting: file_path=%s project_id=%s",
            file_path,
            project_id,
        )
        try:
            # Resolve project root via canonical 3-component scheme.
            from code_analysis.core.database.watch_dirs_partition import (
                current_server_instance_id,
            )
            from code_analysis.core.database.watch_dirs_query import (
                _database_query_rows,
            )

            sid = current_server_instance_id()
            rows = _database_query_rows(
                self.driver,
                """
                SELECT p.root_path, p.watch_dir_id, p.name,
                       w.absolute_path AS watch_absolute_path
                FROM projects p
                LEFT JOIN watch_dir_paths w
                  ON w.server_instance_id = p.server_instance_id
                 AND w.watch_dir_id = p.watch_dir_id
                WHERE p.server_instance_id = ? AND p.id = ?
                """,
                (sid, project_id),
            )
            exec_result = {"data": rows}
            data = exec_result.get("data") if isinstance(exec_result, dict) else None
            if not data or len(data) == 0:
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Project not found: {project_id}",
                )
            row = data[0]
            watch_abs = row.get("watch_absolute_path")
            proj_name = row.get("name")
            root_path_stored = row.get("root_path")

            # Build absolute root: prefer canonical watch_abs / proj_name;
            # fall back to resolve_projects_root_path_row_to_absolute_str for legacy rows.
            from code_analysis.core.project_root_path import (
                resolve_projects_root_path_row_to_absolute_str,
            )

            if watch_abs and proj_name:
                abs_root_str = str(Path(watch_abs) / proj_name)
            else:
                abs_root_str = resolve_projects_root_path_row_to_absolute_str(
                    root_path_stored=root_path_stored,
                    watch_dir_id=row.get("watch_dir_id"),
                    database=self.driver,
                )

            if not abs_root_str:
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Cannot resolve absolute root for project: {project_id}",
                )

            # Reuse existing driver: update_file_data_via_driver uses InProcessRpcClient
            # over this driver (no second legacy SQL facade wrapper with sync_schema in this process).
            try:
                from code_analysis.core.database.files.update_standalone import (
                    update_file_data_via_driver,
                )

                logger.debug(
                    "[index_file] Using update_file_data_via_driver (no extra DB wrapper)"
                )
                docs_indexing = (
                    params.get("docs_indexing") if isinstance(params, dict) else None
                )
                server_config_path = (
                    params.get("server_config_path")
                    if isinstance(params, dict)
                    else None
                )
                if docs_indexing is not None and not isinstance(docs_indexing, dict):
                    docs_indexing = None
                if server_config_path is not None and not isinstance(
                    server_config_path, str
                ):
                    server_config_path = None
                skip_file_edit_lock = bool(
                    params.get("skip_file_edit_lock")
                    if isinstance(params, dict)
                    else False
                )

                update_result = update_file_data_via_driver(
                    driver=self.driver,
                    file_path=file_path,
                    project_id=project_id,
                    root_dir=Path(abs_root_str),
                    docs_indexing=docs_indexing,
                    server_config_path=server_config_path,
                    skip_file_edit_lock=skip_file_edit_lock,
                )
            except Exception as e:
                if not _is_fk_or_integrity_error(e):
                    raise
                logger.warning(
                    "[index_file] FK/integrity (project likely deleted): project_id=%s %s",
                    project_id,
                    e,
                )
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description="Project no longer exists (deleted during indexing)",
                )

            if not update_result.get("success"):
                error_msg = update_result.get("error", "Unknown error")
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=error_msg,
                )

            # Clear needs_chunking only when full reindex was performed (not skipped).
            abs_path = update_result.get("file_path", file_path)
            fp_param = str(file_path)
            abs_resolved = str(abs_path)
            if not update_result.get("skipped"):
                try:
                    self.driver.execute(
                        "UPDATE files SET needs_chunking = 0 WHERE project_id = ?"
                        " AND (path = ? OR path = ? OR relative_path = ? OR relative_path = ?)",
                        (project_id, fp_param, abs_resolved, fp_param, abs_resolved),
                        None,
                    )
                except Exception as e:
                    if _is_fk_or_integrity_error(e):
                        logger.warning(
                            "[index_file] FK on needs_chunking (project deleted): %s",
                            abs_path,
                        )
                        return ErrorResult(
                            error_code=ErrorCode.NOT_FOUND,
                            description="Project no longer exists (deleted during indexing)",
                        )
                    logger.warning(
                        "Failed to clear needs_chunking after index_file for %s: %s",
                        abs_path,
                        e,
                    )
                    # Still return success; index completed.

            # Clear indexing error for this file on successful write.
            try:
                self.driver.execute(
                    "DELETE FROM indexing_errors WHERE project_id = ? AND (file_path = ? OR file_path = ?)",
                    (project_id, fp_param, abs_resolved),
                    None,
                )
            except Exception:
                pass  # Best-effort cleanup; ignore FK/IO errors.

            logger.debug(
                "[index_file] Completed: file_path=%s success=True",
                update_result.get("file_path", file_path),
            )
            return SuccessResult(data=update_result)
        except Exception as e:
            if _is_fk_or_integrity_error(e):
                logger.warning(
                    "[index_file] FK/integrity (project likely deleted): %s", e
                )
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description="Project no longer exists (deleted during indexing)",
                )
            err_msg = str(e)
            logger.error("index_file failed for %s: %s", file_path, e, exc_info=True)
            if "temp_files" in err_msg:
                logger.error("[index_file] temp_files-related failure: %s", err_msg)
            return ErrorResult(error_code=ErrorCode.DATABASE_ERROR, description=err_msg)
