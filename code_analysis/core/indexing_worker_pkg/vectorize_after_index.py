"""
Vectorize file after index: chunk and embed so vectorization worker can transfer to FAISS.

Called by the indexing worker after each successful index_file() to fill embedding_vector
for the file's chunks. The vectorization worker then only transfers (adds to FAISS).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from code_analysis.core.docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES

logger = logging.getLogger(__name__)


def vectorize_file_after_index(
    db_path: Path,
    config_path: str,
    file_path: str,
    project_id: str,
    file_id: int,
) -> Dict[str, Any]:
    """Run chunking and embedding for a file after it was indexed (so vectors are ready for transfer).

    Uses DatabaseClient via InProcessRpcClient + SVOClientManager to run
    vectorize_file_immediately.
    On failure logs and returns; does not raise (index already succeeded).

    Args:
        db_path: Path to database file.
        config_path: Path to config file (for chunker/embedding).
        file_path: Absolute file path (from DB).
        project_id: Project UUID.
        file_id: File ID in DB.

    Returns:
        Result dict from vectorize_file_immediately or {"success": False, "error": str}.
    """
    try:
        config_data = _load_config(config_path)
        if not config_data:
            return {"success": False, "error": "Could not load config"}

        db = _create_database(db_path)
        if db is None:
            return {"success": False, "error": "Could not create database"}

        svo_manager = _create_svo_manager(config_data, config_path)
        if svo_manager is None:
            logger.debug("No chunker/embedding config, skipping vectorize after index")
            return {"success": False, "error": "No chunker config"}

        try:
            result = asyncio.run(
                _vectorize_file_immediately(
                    db, file_id, project_id, file_path, svo_manager
                )
            )
            return result or {"success": False, "error": "No result"}
        finally:
            _close_driver(db)
    except Exception as e:
        logger.warning(
            "Vectorize after index failed for file_id=%s path=%s: %s",
            file_id,
            file_path,
            e,
        )
        return {"success": False, "error": str(e)}


def _load_config(config_path: str) -> Optional[Dict[str, Any]]:
    """Load config dict from path."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load config from %s: %s", config_path, e)
        return None


def _create_database(db_path: Path) -> Any:
    """Create DatabaseClient using InProcessRpcClient over a local SQLiteDriver."""
    try:
        from code_analysis.core.database_client.client import DatabaseClient
        from code_analysis.core.database_client.in_process_rpc_client import (
            InProcessRpcClient,
        )
        from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver
        from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

        driver = SQLiteDriver()
        driver.connect({"path": str(db_path.resolve())})
        handlers = RPCHandlers(driver)
        ipc = InProcessRpcClient(handlers)
        ipc.connect()
        client = DatabaseClient(rpc_client=ipc, driver_type="sqlite")
        return client
    except Exception as e:
        logger.warning("Could not create database for %s: %s", db_path, e)
        return None


def _create_svo_manager(config_data: Dict[str, Any], config_path: str) -> Optional[Any]:
    """Create SVOClientManager from full config (chunker/embedding)."""
    try:
        from code_analysis.core.vectorization_helper import get_svo_client_manager

        root_dir = Path(config_path).resolve().parent
        return get_svo_client_manager(config_data, root_dir)
    except Exception as e:
        logger.debug("Could not create SVO client manager: %s", e)
        return None


async def _vectorize_file_immediately(
    db: Any,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Any,
) -> Dict[str, Any]:
    """Vectorize via standalone function (db is DatabaseClient after step 06)."""
    if Path(file_path).suffix.lower() in DOCS_INDEX_FILE_SUFFIXES:
        return {
            "success": True,
            "chunked": False,
            "chunks_created": 0,
            "vectorized": False,
            "marked_for_worker": False,
            "error": None,
        }

    from code_analysis.core.database.files.update_standalone import (
        _vectorize_via_client,
    )

    await svo_client_manager.initialize()
    try:
        return await _vectorize_via_client(
            client=db,
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            svo_client_manager=svo_client_manager,
            faiss_manager=None,
        )
    finally:
        await svo_client_manager.close()


def _close_driver(db: Any) -> None:
    """Disconnect InProcessRpcClient (also disconnects the underlying SQLiteDriver)."""
    try:
        rpc_client = getattr(db, "rpc_client", None)
        if rpc_client is not None:
            rpc_client.disconnect()
    except Exception as e:
        logger.debug("Error disconnecting rpc_client: %s", e)
