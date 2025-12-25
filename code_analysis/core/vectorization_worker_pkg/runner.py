"""
Module runner.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .base import VectorizationWorker

logger = logging.getLogger(__name__)


def run_vectorization_worker(
    db_path: str,
    project_id: str,
    faiss_index_path: str,
    vector_dim: int,
    svo_config: Optional[Dict[str, Any]] = None,
    batch_size: int = 10,
    poll_interval: int = 30,
    retry_attempts: int = 3,
    retry_delay: float = 10.0,
) -> Dict[str, Any]:
    """
    Run vectorization worker in separate process with continuous polling.

    This function is designed to be called from multiprocessing.Process.
    It runs indefinitely, checking for chunks to vectorize at specified intervals.

    Args:
        db_path: Path to database file
        project_id: Project ID to process
        faiss_index_path: Path to FAISS index file
        vector_dim: Vector dimension
        svo_config: SVO client configuration (optional)
        batch_size: Batch size for processing
        poll_interval: Interval in seconds between polling cycles (default: 30)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    from ..config import ServerConfig
    from ..faiss_manager import FaissIndexManager
    from ..svo_client_manager import SVOClientManager

    logger.info(
        f"Starting continuous vectorization worker for project {project_id}, "
        f"poll interval: {poll_interval}s"
    )

    # Initialize SVO client manager if config provided
    svo_client_manager = None
    if svo_config:
        try:
            server_config_obj = ServerConfig(**svo_config)
            svo_client_manager = SVOClientManager(server_config_obj)
            asyncio.run(svo_client_manager.initialize())
        except Exception as e:
            logger.error(f"Failed to initialize SVO client manager: {e}")
            return {"processed": 0, "errors": 1}

    # Initialize FAISS manager
    try:
        faiss_manager = FaissIndexManager(
            index_path=faiss_index_path,
            vector_dim=vector_dim,
        )
    except Exception as e:
        logger.error(f"Failed to initialize FAISS manager: {e}")
        if svo_client_manager:
            asyncio.run(svo_client_manager.close())
        return {"processed": 0, "errors": 1}

    # Get retry config and min_chunk_length from svo_config if available
    min_chunk_length = 30  # default
    if svo_config:
        try:
            server_config_obj = ServerConfig(**svo_config)
            if hasattr(server_config_obj, "vectorization_retry_attempts"):
                retry_attempts = server_config_obj.vectorization_retry_attempts
            if hasattr(server_config_obj, "vectorization_retry_delay"):
                retry_delay = server_config_obj.vectorization_retry_delay
            if hasattr(server_config_obj, "min_chunk_length"):
                min_chunk_length = server_config_obj.min_chunk_length
        except Exception:
            pass  # Use defaults

    # Create and run worker
    worker = VectorizationWorker(
        db_path=Path(db_path),
        project_id=project_id,
        svo_client_manager=svo_client_manager,
        faiss_manager=faiss_manager,
        batch_size=batch_size,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        min_chunk_length=min_chunk_length,
    )

    try:
        result = asyncio.run(worker.process_chunks(poll_interval=poll_interval))
        return result
    except KeyboardInterrupt:
        logger.info("Vectorization worker interrupted by signal")
        worker.stop()
        return {"processed": 0, "errors": 0, "interrupted": True}
    except Exception as e:
        logger.error(f"Error in vectorization worker: {e}", exc_info=True)
        return {"processed": 0, "errors": 1}
    finally:
        if svo_client_manager:
            asyncio.run(svo_client_manager.close())
