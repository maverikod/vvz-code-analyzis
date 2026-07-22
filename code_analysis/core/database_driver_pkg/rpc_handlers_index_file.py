"""
RPC handler for index_file: full file index (AST, CST, entities, code_content) in driver process.

Exposes "index_file" RPC used by the indexing worker. Thin delegate to
:func:`~code_analysis.core.database.files.update_standalone.index_file_via_driver`
(Stage 2 layer collapse relocated the composite logic — project-root resolution,
needs_chunking/indexing_errors cleanup, FK/integrity classification — there; this
handler only maps :class:`~code_analysis.core.database.files.update_standalone.IndexFileError`
back onto the RPC :class:`ErrorResult` shape).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from code_analysis.core.database_client.protocol import (
    ErrorResult,
    SuccessResult,
    ErrorCode,
)
from code_analysis.core.database.files.update_standalone import (
    IndexFileError,
    index_file_via_driver,
)

logger = logging.getLogger(__name__)


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
        docs_indexing = (
            params.get("docs_indexing") if isinstance(params, dict) else None
        )
        server_config_path = (
            params.get("server_config_path") if isinstance(params, dict) else None
        )
        if docs_indexing is not None and not isinstance(docs_indexing, dict):
            docs_indexing = None
        if server_config_path is not None and not isinstance(server_config_path, str):
            server_config_path = None
        skip_file_edit_lock = bool(
            params.get("skip_file_edit_lock") if isinstance(params, dict) else False
        )

        try:
            update_result = index_file_via_driver(
                self.driver,
                file_path=file_path,
                project_id=project_id,
                docs_indexing=docs_indexing,
                server_config_path=server_config_path,
                skip_file_edit_lock=skip_file_edit_lock,
            )
        except IndexFileError as e:
            error_code = (
                ErrorCode.NOT_FOUND
                if e.error_code == "NOT_FOUND"
                else ErrorCode.DATABASE_ERROR
            )
            return ErrorResult(error_code=error_code, description=str(e))
        return SuccessResult(data=update_result)
