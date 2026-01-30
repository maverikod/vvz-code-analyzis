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
    faiss_dir: str,
    vector_dim: int,
    svo_config: Optional[Dict[str, Any]] = None,
    batch_size: int = 10,
    poll_interval: int = 30,
    retry_attempts: int = 3,
    retry_delay: float = 10.0,
    worker_log_path: Optional[str] = None,
    pid_file_path: Optional[str] = None,
    log_max_bytes: int = 10485760,  # 10 MB default
    log_backup_count: int = 5,
) -> Dict[str, Any]:
    """
    Run universal vectorization worker in separate process with continuous polling.

    Worker operates in universal mode - processes all projects from database.
    Worker works only with database - no filesystem access, no watch_dirs.
    Worker periodically queries database to discover projects with files/chunks needing vectorization.

    This function is designed to be called from multiprocessing.Process.
    It runs indefinitely, checking for chunks to vectorize at specified intervals.

    Args:
        db_path: Path to database file
        faiss_dir: Base directory for FAISS index files (project-scoped indexes: {faiss_dir}/{project_id}.bin)
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
        f"Starting universal vectorization worker, "
        f"poll interval: {poll_interval}s, "
        f"FAISS directory: {faiss_dir}"
    )

    # Database auto-creation (if database doesn't exist, create it)
    from ..database_client.client import DatabaseClient
    from ..constants import DEFAULT_DB_DRIVER_SOCKET_DIR

    db_path_obj = Path(db_path)

    # Ensure parent directory exists
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Get socket path for database driver
    db_name = db_path_obj.stem
    socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
    socket_dir.mkdir(parents=True, exist_ok=True)
    socket_path = str(socket_dir / f"{db_name}_driver.sock")

    # Check if database exists, create if not
    if not db_path_obj.exists():
        logger.info(f"Database file not found, creating new database at {db_path}")
        try:
            init_database = DatabaseClient(socket_path=socket_path)
            init_database.connect()
            init_database.disconnect()
            logger.info(f"Created new database at {db_path}")
        except Exception as e:
            logger.warning(f"Failed to create database: {e}, continuing anyway")

    # Initialize SVO client manager if config provided
    svo_client_manager = None
    logger.info(
        f"SVO config provided: {svo_config is not None}, type: {type(svo_config)}"
    )
    if svo_config:
        try:
            logger.info(
                f"Creating ServerConfig from svo_config, keys: {list(svo_config.keys()) if isinstance(svo_config, dict) else 'not a dict'}"
            )
            server_config_obj = ServerConfig(**svo_config)
            logger.info("Creating SVOClientManager...")
            svo_client_manager = SVOClientManager(server_config_obj)
            logger.info("Initializing SVOClientManager...")
            asyncio.run(svo_client_manager.initialize())
            logger.info("SVOClientManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SVO client manager: {e}", exc_info=True)
            return {"processed": 0, "errors": 1}
    else:
        logger.warning(
            "No svo_config provided, SVO client manager will not be initialized"
        )

    # FAISS index sync check for all projects at startup
    try:
        logger.info(
            "Checking FAISS index synchronization with database for all projects..."
        )
        try:
            sync_database = DatabaseClient(socket_path=socket_path, timeout=30.0)
            sync_database.connect()
            # Get all projects from database
            all_projects = sync_database.list_projects()
            # Convert Project objects to dict format for compatibility
            all_projects = [
                {
                    "id": p.id,
                    "root_path": p.root_path,
                    "name": p.name,
                    "comment": p.comment,
                }
                for p in all_projects
            ]

            if not all_projects:
                logger.info("No projects found in database, skipping FAISS sync check")
            else:
                logger.info(
                    f"Checking FAISS index sync for {len(all_projects)} projects..."
                )
                faiss_dir_path = Path(faiss_dir)

                for project in all_projects:
                    project_id = project["id"]
                    project_path = project.get("root_path", "unknown")

                    # Get project-scoped FAISS index path
                    index_path = faiss_dir_path / f"{project_id}.bin"

                    try:
                        # Create FAISS manager for this project
                        faiss_manager = FaissIndexManager(
                            index_path=str(index_path),
                            vector_dim=vector_dim,
                        )

                        # Check sync (datasets EXCLUDED)
                        is_synced, sync_details = faiss_manager.check_index_sync(
                            database=sync_database,
                            project_id=project_id,
                        )

                        if not is_synced:
                            logger.warning(
                                f"⚠️  FAISS index synchronization check failed for project {project_id} ({project_path}):"
                            )
                            logger.warning(
                                f"   Database vectors: {sync_details['db_vector_count']}, "
                                f"Index vectors: {sync_details['index_vector_count']}"
                            )
                            if sync_details.get("missing_in_index_count", 0) > 0:
                                logger.warning(
                                    f"   Missing in index: {sync_details['missing_in_index_count']} vectors "
                                    f"(sample: {sync_details['missing_in_index'][:10]})"
                                )
                            if sync_details.get("extra_in_index_count", 0) > 0:
                                logger.warning(
                                    f"   Extra in index: {sync_details['extra_in_index_count']} vectors "
                                    f"(sample: {sync_details['extra_in_index'][:10]})"
                                )

                            logger.info(
                                f"🔄 Rebuilding FAISS index from database for project {project_id}..."
                            )
                            # Rebuild index from database (datasets EXCLUDED)
                            vectors_count = asyncio.run(
                                faiss_manager.rebuild_from_database(
                                    database=sync_database,
                                    svo_client_manager=svo_client_manager,
                                    project_id=project_id,
                                )
                            )
                            logger.info(
                                f"✅ FAISS index rebuilt: {vectors_count} vectors loaded for project {project_id}"
                            )
                        else:
                            logger.info(
                                f"✅ FAISS index is synchronized with database for project {project_id}: "
                                f"{sync_details['index_vector_count']} vectors"
                            )

                        # Close FAISS manager
                        faiss_manager = None
                    except Exception as project_e:
                        logger.warning(
                            f"Failed to check/rebuild FAISS index for project {project_id}: {project_e}",
                            exc_info=True,
                        )
                        # Continue with next project

            sync_database.disconnect()
        except Exception as db_e:
            logger.warning(
                f"⚠️  Database is unavailable during startup sync check: {db_e}. "
                "Skipping index synchronization check. Worker will retry when database becomes available."
            )
    except Exception as e:
        logger.warning(
            f"Failed to check FAISS index synchronization: {e}. "
            "Continuing with worker startup, but indexes may be out of sync.",
            exc_info=True,
        )
        # Continue anyway - worker can still function, but indexes may need manual rebuild

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

    # Create and run worker (universal mode - no project_id, no faiss_manager at init)
    # Pass socket_path to worker for DatabaseClient initialization
    worker = VectorizationWorker(
        db_path=Path(db_path),
        faiss_dir=Path(faiss_dir),
        vector_dim=vector_dim,
        svo_client_manager=svo_client_manager,
        batch_size=batch_size,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        min_chunk_length=min_chunk_length,
        max_empty_iterations=max_empty_iterations,
        empty_delay=empty_delay,
        socket_path=socket_path,  # Pass socket_path for DatabaseClient
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
        # Remove PID file on exit so next start is not blocked by stale PID
        if pid_file_path and Path(pid_file_path).exists():
            try:
                Path(pid_file_path).unlink()
                logger.debug(f"Removed PID file on exit: {pid_file_path}")
            except Exception as e:
                logger.warning(f"Could not remove PID file {pid_file_path}: {e}")
