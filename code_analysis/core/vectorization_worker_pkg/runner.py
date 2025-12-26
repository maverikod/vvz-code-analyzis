"""
Module runner.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from .base import VectorizationWorker

logger = logging.getLogger(__name__)


def _setup_worker_logging(
    log_path: Optional[str] = None,
    max_bytes: int = 10485760,  # 10 MB default
    backup_count: int = 5,
) -> None:
    """
    Setup logging for vectorization worker to separate log file with rotation.

    Args:
        log_path: Path to worker log file (optional)
        max_bytes: Maximum log file size in bytes before rotation (default: 10 MB)
        backup_count: Number of backup log files to keep (default: 5)
    """
    if log_path:
        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger for worker process
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Rotating file handler for worker log
        file_handler = RotatingFileHandler(
            log_file,
            encoding="utf-8",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Also log to stderr for visibility
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        logger.info(f"Worker logging configured: {log_file}")
    else:
        # Default logging if no path specified
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )


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
    worker_log_path: Optional[str] = None,
    log_max_bytes: int = 10485760,  # 10 MB default
    log_backup_count: int = 5,
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
        worker_log_path: Path to worker log file (optional)
        log_max_bytes: Maximum log file size in bytes before rotation (default: 10 MB)
        log_backup_count: Number of backup log files to keep (default: 5)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    from ..config import ServerConfig
    from ..faiss_manager import FaissIndexManager
    from ..svo_client_manager import SVOClientManager

    # Setup worker logging first
    _setup_worker_logging(worker_log_path, log_max_bytes, log_backup_count)

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

    # Get retry config, min_chunk_length, and batch_processor config from svo_config if available
    min_chunk_length = 30  # default
    max_empty_iterations = 3  # default
    empty_delay = 5.0  # default
    if svo_config:
        try:
            server_config_obj = ServerConfig(**svo_config)
            if hasattr(server_config_obj, "vectorization_retry_attempts"):
                retry_attempts = server_config_obj.vectorization_retry_attempts
            if hasattr(server_config_obj, "vectorization_retry_delay"):
                retry_delay = server_config_obj.vectorization_retry_delay
            if hasattr(server_config_obj, "min_chunk_length"):
                min_chunk_length = server_config_obj.min_chunk_length
            # Get batch_processor config and log_path from worker config
            if hasattr(server_config_obj, "worker") and server_config_obj.worker:
                worker_config = server_config_obj.worker
                if isinstance(worker_config, dict):
                    batch_processor_config = worker_config.get("batch_processor", {})
                    max_empty_iterations = batch_processor_config.get(
                        "max_empty_iterations", 3
                    )
                    empty_delay = batch_processor_config.get("empty_delay", 5.0)
                    # Get worker log path
                    if worker_log_path is None:
                        worker_log_path = worker_config.get("log_path")
                    # Get log rotation config
                    log_rotation_config = worker_config.get("log_rotation", {})
                    if log_rotation_config:
                        log_max_bytes = log_rotation_config.get("max_bytes", 10485760)
                        log_backup_count = log_rotation_config.get("backup_count", 5)
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
        max_empty_iterations=max_empty_iterations,
        empty_delay=empty_delay,
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
