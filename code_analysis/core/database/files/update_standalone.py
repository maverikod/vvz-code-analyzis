"""
Standalone file reindex via BaseDatabaseDriver, driver-direct (stage 2).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from code_analysis.core.database_driver_pkg.drivers.base import BaseDatabaseDriver
from code_analysis.core.docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES

logger = logging.getLogger(__name__)


class IndexFileError(Exception):
    """Raised by :func:`index_file_via_driver` on any failure.

    Carries ``error_code`` (``"NOT_FOUND"`` | ``"DATABASE_ERROR"`` | ``"VALIDATION_ERROR"``)
    so callers that need to reproduce the previous RPC ``ErrorResult`` mapping
    (:mod:`~code_analysis.core.database_driver_pkg.rpc_handlers_index_file`, now a thin
    delegate to this function) can do so exactly.
    """

    def __init__(self, message: str, error_code: str = "DATABASE_ERROR") -> None:
        super().__init__(message)
        self.error_code = error_code


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


def _analyze_result_to_update_file_data_dict(
    raw: Dict[str, Any], abs_file_path: str
) -> Dict[str, Any]:
    """Map :func:`analyze_file` result to :meth:`CodeDatabase.update_file_data` dict shape."""
    if raw.get("success") is not None and "status" not in raw:
        return raw
    status = raw.get("status")
    if status == "success":
        out: Dict[str, Any] = {
            "success": True,
            "file_path": abs_file_path,
            "skipped": False,
        }
        if raw.get("entities_updated") is not None:
            out["entities_updated"] = raw["entities_updated"]
        return out
    if status == "skipped":
        return {
            "success": True,
            "file_path": abs_file_path,
            "skipped": True,
        }
    if status in ("error", "syntax_error"):
        return {
            "success": False,
            "error": raw.get("error", "Unknown error"),
            "file_path": abs_file_path,
        }
    return {
        "success": False,
        "error": raw.get("error", f"Unexpected analyze status: {status!r}"),
        "file_path": abs_file_path,
    }


def update_file_data_via_driver(
    driver: BaseDatabaseDriver,
    file_path: str,
    project_id: str,
    root_dir: Path,
    *,
    docs_indexing: Optional[Dict[str, Any]] = None,
    server_config_path: Optional[str] = None,
    skip_file_edit_lock: bool = False,
) -> Dict[str, Any]:
    """
    Update database records for a file using a :class:`BaseDatabaseDriver`.

    Hands ``driver`` straight to :func:`~code_analysis.commands.update_indexes_analyzer.analyze_file`
    (driver-direct, stage 2 layer collapse — no DatabaseClient/RPC bridge).
    Prefer this in driver-owning processes instead of :meth:`CodeDatabase.update_file_data`.

    Args:
        driver: Connected database driver (e.g. SQLite or PostgreSQL).
        file_path: Path to the file (absolute or resolvable from ``root_dir``).
        project_id: Project UUID.
        root_dir: Project root directory.
        skip_file_edit_lock: Passed through to :func:`~code_analysis.commands.update_indexes_analyzer.analyze_file`.

    Returns:
        Per-file dict in the same shape as :meth:`CodeDatabase.update_file_data`
        (``success``, ``file_path``, optional ``skipped``, ``error``, …).
    """
    from code_analysis.commands.update_indexes_analyzer import analyze_file

    path_obj = Path(file_path)
    raw = analyze_file(
        database=driver,
        file_path=path_obj,
        project_id=project_id,
        root_path=root_dir,
        force=True,
        docs_indexing=docs_indexing,
        server_config_path=server_config_path,
        skip_file_edit_lock=skip_file_edit_lock,
    )
    return _analyze_result_to_update_file_data_dict(raw, str(path_obj.resolve()))


def index_file_via_driver(
    driver: BaseDatabaseDriver,
    file_path: str,
    project_id: str,
    *,
    docs_indexing: Optional[Dict[str, Any]] = None,
    server_config_path: Optional[str] = None,
    skip_file_edit_lock: bool = False,
) -> Dict[str, Any]:
    """
    Full file index (AST, CST, entities, code_content) directly on ``driver``.

    Stage-2 layer collapse: relocated verbatim from the RPC ``index_file`` handler
    (:mod:`~code_analysis.core.database_driver_pkg.rpc_handlers_index_file`, which is
    now a thin delegate to this function) so the whole ``index_file`` operation is one
    driver-package function instead of split across a handler file and this module.

    Resolves the project root via the canonical 3-component scheme
    (watch_dir_paths.absolute_path / projects.name / files.relative_path), calls
    :func:`update_file_data_via_driver`, then clears ``needs_chunking`` and any
    stale ``indexing_errors`` row for the file on success.

    Args:
        driver: Connected database driver (PostgreSQL).
        file_path: Path to the file (project-relative or absolute).
        project_id: Project UUID.
        docs_indexing: When set, enables the documentation file path in ``analyze_file``.
        server_config_path: Server ``config.json`` for optional SVO chunking (docs path).
        skip_file_edit_lock: When True, caller already holds ``files.editing_pid``.

    Returns:
        Update-result dict (``success`` always True; ``file_id``, ``file_path``,
        ``ast_updated``, ``cst_updated``, ``entities_updated`` per :func:`update_file_data_via_driver`).

    Raises:
        IndexFileError: On any failure (project not found, unresolvable root, FK/integrity
            race during write, or a non-success result from :func:`update_file_data_via_driver`).
            ``error_code`` is ``"NOT_FOUND"`` for FK/integrity races, ``"DATABASE_ERROR"`` otherwise
            — mirrors the previous RPC ``ErrorResult`` mapping exactly.
    """
    from code_analysis.core.database.watch_dirs_partition import (
        current_server_instance_id,
    )
    from code_analysis.core.database.watch_dirs_query import _database_query_rows
    from code_analysis.core.project_root_path import (
        resolve_projects_root_path_row_to_absolute_str,
    )

    logger.debug(
        "[index_file] Starting: file_path=%s project_id=%s", file_path, project_id
    )

    try:
        sid = current_server_instance_id()
        rows = _database_query_rows(
            driver,
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
        if not rows:
            raise IndexFileError(
                f"Project not found: {project_id}", error_code="DATABASE_ERROR"
            )
        row = rows[0]
        watch_abs = row.get("watch_absolute_path")
        proj_name = row.get("name")
        root_path_stored = row.get("root_path")

        if watch_abs and proj_name:
            abs_root_str = str(Path(watch_abs) / proj_name)
        else:
            abs_root_str = resolve_projects_root_path_row_to_absolute_str(
                root_path_stored=root_path_stored,
                watch_dir_id=row.get("watch_dir_id"),
                database=driver,
            )

        if not abs_root_str:
            raise IndexFileError(
                f"Cannot resolve absolute root for project: {project_id}",
                error_code="DATABASE_ERROR",
            )

        try:
            update_result = update_file_data_via_driver(
                driver=driver,
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
            raise IndexFileError(
                "Project no longer exists (deleted during indexing)",
                error_code="NOT_FOUND",
            ) from e

        if not update_result.get("success"):
            raise IndexFileError(
                update_result.get("error", "Unknown error"),
                error_code="DATABASE_ERROR",
            )

        # Clear needs_chunking only when full reindex was performed (not skipped).
        abs_path = update_result.get("file_path", file_path)
        fp_param = str(file_path)
        abs_resolved = str(abs_path)
        if not update_result.get("skipped"):
            try:
                driver.execute(
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
                    raise IndexFileError(
                        "Project no longer exists (deleted during indexing)",
                        error_code="NOT_FOUND",
                    ) from e
                logger.warning(
                    "Failed to clear needs_chunking after index_file for %s: %s",
                    abs_path,
                    e,
                )
                # Still return success; index completed.

        # Clear indexing error for this file on successful write.
        try:
            driver.execute(
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
        return update_result
    except IndexFileError:
        raise
    except Exception as e:
        if _is_fk_or_integrity_error(e):
            logger.warning("[index_file] FK/integrity (project likely deleted): %s", e)
            raise IndexFileError(
                "Project no longer exists (deleted during indexing)",
                error_code="NOT_FOUND",
            ) from e
        err_msg = str(e)
        logger.error("index_file failed for %s: %s", file_path, e, exc_info=True)
        if "temp_files" in err_msg:
            logger.error("[index_file] temp_files-related failure: %s", err_msg)
        raise IndexFileError(err_msg, error_code="DATABASE_ERROR") from e


async def _vectorize_via_client(
    client: Any,
    file_id: Any,
    project_id: str,
    file_path: str,
    svo_client_manager: Any,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Vectorize a file immediately using a DatabaseClient.

    Thin wrapper: passes the client to DocstringChunker as ``database``.
    DocstringChunker already supports DatabaseClient via its dual-path
    ``_file_still_exists_and_not_deleted`` and ``_persist_code_chunk_param_rows``.

    Args:
        client: DatabaseClient instance (already connected).
        file_id: File ID in the database.
        project_id: Project UUID.
        file_path: Absolute path to the file.
        svo_client_manager: SVO client manager for embeddings.
        faiss_manager: Optional FAISS manager (reserved, not used directly).

    Returns:
        Result dict: {success, chunked, chunks_created, vectorized,
                      marked_for_worker, error}.
    """
    from code_analysis.core.docstring_chunker_pkg.docstring_chunker import (
        DocstringChunker,
    )

    if not svo_client_manager:
        client.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": True,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": True,
            "error": None,
        }

    try:
        try:
            db_project = client.get_project(project_id)
            if db_project:
                _ = Path(db_project["root_path"])  # reserved for path normalization
        except Exception as e:
            logger.debug("Could not get project root: %s", e)

        file_path_obj = Path(file_path)
        if file_path_obj.suffix.lower() in DOCS_INDEX_FILE_SUFFIXES:
            return {
                "success": True,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": False,
                "error": None,
            }

        if not file_path_obj.exists():
            client.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": True,
                "error": "File not found",
            }

        file_content = file_path_obj.read_text(encoding="utf-8")

        try:
            tree = ast.parse(file_content, filename=file_path)
        except SyntaxError as e:
            client.mark_file_needs_chunking(file_path, project_id)
            return {
                "success": False,
                "chunked": False,
                "chunks_created": 0,
                "vectorized": False,
                "marked_for_worker": True,
                "error": f"Syntax error: {e}",
            }

        chunker = DocstringChunker(
            database=client,
            svo_client_manager=svo_client_manager,
            faiss_manager=faiss_manager,
            min_chunk_length=30,
        )

        chunks_created = await chunker.process_file(
            file_id=str(file_id),
            project_id=project_id,
            file_path=file_path,
            tree=tree,
            file_content=file_content,
        )

        return {
            "success": True,
            "chunked": True,
            "chunks_created": chunks_created,
            "vectorized": chunks_created > 0,
            "marked_for_worker": False,
            "error": None,
        }

    except Exception as e:
        logger.error(
            "Error in _vectorize_via_client for %s: %s", file_path, e, exc_info=True
        )
        client.mark_file_needs_chunking(file_path, project_id)
        return {
            "success": False,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": True,
            "error": str(e),
        }
