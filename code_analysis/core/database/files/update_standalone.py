"""
Standalone file reindex via BaseDatabaseDriver and DatabaseClient.

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


def _driver_type_for_inprocess_client(driver: BaseDatabaseDriver) -> Optional[str]:
    """Infer :class:`DatabaseClient` ``driver_type`` for portable SQL (PostgreSQL only)."""
    from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver

    if isinstance(driver, PostgreSQLDriver):
        return "postgres"
    return None


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

    Builds an in-process :class:`~code_analysis.core.database_client.client.DatabaseClient`
    over ``driver`` and delegates to :func:`~code_analysis.commands.update_indexes_analyzer.analyze_file`.
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
    from code_analysis.core.database_client.client import DatabaseClient
    from code_analysis.core.database_client.in_process_rpc_client import (
        InProcessRpcClient,
    )
    from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

    handlers = RPCHandlers(driver)
    ipc = InProcessRpcClient(handlers)
    ipc.connect()
    client = DatabaseClient(
        rpc_client=ipc,
        driver_type=_driver_type_for_inprocess_client(driver),
    )
    try:
        path_obj = Path(file_path)
        raw = analyze_file(
            database=client,
            file_path=path_obj,
            project_id=project_id,
            root_path=root_dir,
            force=True,
            docs_indexing=docs_indexing,
            server_config_path=server_config_path,
            skip_file_edit_lock=skip_file_edit_lock,
        )
        return _analyze_result_to_update_file_data_dict(raw, str(path_obj.resolve()))
    finally:
        ipc.disconnect(close_driver=False)


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
