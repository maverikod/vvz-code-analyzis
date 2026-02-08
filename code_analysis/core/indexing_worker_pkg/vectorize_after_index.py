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

logger = logging.getLogger(__name__)


def vectorize_file_after_index(
    db_path: Path,
    config_path: str,
    file_path: str,
    project_id: str,
    file_id: int,
) -> Dict[str, Any]:
    """Run chunking and embedding for a file after it was indexed (so vectors are ready for transfer).

    Uses direct CodeDatabase + SVOClientManager to run vectorize_file_immediately.
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
    """Create CodeDatabase using direct SQLite driver (same process as indexer)."""
    try:
        from code_analysis.core.database import CodeDatabase
        from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver

        driver = SQLiteDriver()
        driver.connect({"path": str(db_path.resolve())})
        return CodeDatabase.from_existing_driver(driver)
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
    """Thin wrapper around database.vectorize_file_immediately."""
    await svo_client_manager.initialize()
    try:
        return await db.vectorize_file_immediately(
            file_id=file_id,
            project_id=project_id,
            file_path=file_path,
            svo_client_manager=svo_client_manager,
            faiss_manager=None,
        )
    finally:
        await svo_client_manager.close()


def _close_driver(db: Any) -> None:
    """Close the driver connection if present."""
    try:
        driver = getattr(db, "driver", None)
        if driver and getattr(driver, "conn", None):
            driver.conn.close()
            driver.conn = None
    except Exception as e:
        logger.debug("Error closing driver: %s", e)
