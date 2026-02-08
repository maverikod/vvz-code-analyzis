"""
MCP command wrappers for starting/stopping background workers.

This module exposes simple control over background workers (file_watcher,
vectorization) via the existing WorkerManager registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.constants import (
    DATA_DIR_NAME,
    DEFAULT_IGNORE_PATTERNS,
    LOGS_DIR_NAME,
)
from ..core.worker_manager import get_worker_manager
from ..core.storage_paths import (
    load_raw_config,
    resolve_storage_paths,
)

logger = logging.getLogger(__name__)


class StartWorkerMCPCommand(BaseMCPCommand):
    """
    Start a background worker process and register it in WorkerManager.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "start_worker"
    version = "1.0.0"
    descr = "Start a background worker (file_watcher or vectorization) for a project"
    category = "worker_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["StartWorkerMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Notes:
            This schema is used by MCP Proxy for request validation.
            Keep it strict and deterministic.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Start a background worker process. "
                "Supported worker_type values: 'file_watcher', 'vectorization', 'indexing'."
            ),
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization", "indexing"],
                    "description": "Type of worker to start.",
                    "examples": ["file_watcher"],
                },
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (used to resolve project root and storage paths).",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "watch_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Directories to watch (file_watcher only; default: project root).",
                    "examples": [["/abs/path/to/project"]],
                },
                "scan_interval": {
                    "type": "integer",
                    "description": "Scan interval seconds (file_watcher only).",
                    "default": 60,
                    "examples": [60],
                },
                "poll_interval": {
                    "type": "integer",
                    "description": "Poll interval seconds (vectorization only).",
                    "default": 30,
                    "examples": [30],
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Batch size (vectorization only).",
                    "default": 10,
                    "examples": [10],
                },
                "vector_dim": {
                    "type": "integer",
                    "description": "Vector dimension (vectorization only).",
                    "default": 384,
                    "examples": [384],
                },
                "worker_log_path": {
                    "type": "string",
                    "description": "Optional log path for the worker process.",
                    "examples": ["/abs/path/to/logs/vectorization_worker.log"],
                },
            },
            "required": ["worker_type", "project_id"],
            "additionalProperties": False,
            "examples": [
                {
                    "worker_type": "file_watcher",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "watch_dirs": ["/abs/path/to/project"],
                    "scan_interval": 60,
                    "worker_log_path": "/abs/path/to/project/logs/file_watcher.log",
                },
                {
                    "worker_type": "vectorization",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "poll_interval": 30,
                    "batch_size": 10,
                    "vector_dim": 384,
                    "worker_log_path": "/abs/path/to/project/logs/vectorization_worker.log",
                },
            ],
        }

    async def execute(
        self: "StartWorkerMCPCommand",
        worker_type: str,
        project_id: str,
        watch_dirs: Optional[List[str]] = None,
        scan_interval: int = 60,
        poll_interval: int = 30,
        batch_size: int = 10,
        vector_dim: int = 384,
        worker_log_path: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute start worker command.

        Args:
            self: Command instance.
            worker_type: Worker type to start.
            project_id: Project UUID (used to resolve project root and storage paths).
            watch_dirs: Optional watch dirs for file watcher (default: project root).
            scan_interval: Scan interval seconds.
            poll_interval: Poll interval seconds.
            batch_size: Vectorization batch size.
            vector_dim: Embedding vector dimension.
            worker_log_path: Optional worker log file path.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with start result or ErrorResult on failure.
        """
        try:
            root_path = self._resolve_project_root(project_id)

            # Resolve service state paths from server config (DB/FAISS/locks).
            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path

            if worker_type == "file_watcher":
                dirs = watch_dirs or [str(root_path)]
                log_path = worker_log_path or str(
                    (root_path / "logs" / "file_watcher.log").resolve()
                )
                worker_logs_dir = str(Path(log_path).resolve().parent)
                worker_manager = get_worker_manager()
                res = worker_manager.start_file_watcher_worker(
                    db_path=str(db_path),
                    watch_dirs=dirs,
                    scan_interval=scan_interval,
                    version_dir=str(
                        (storage.config_dir / "data" / "versions").resolve()
                    ),
                    worker_log_path=log_path,
                    worker_logs_dir=worker_logs_dir,
                    ignore_patterns=list(
                        DEFAULT_IGNORE_PATTERNS | {DATA_DIR_NAME, LOGS_DIR_NAME}
                    ),
                    locks_dir=str(storage.locks_dir),
                )
                return SuccessResult(data=res.__dict__)

            if worker_type == "vectorization":
                log_path = worker_log_path or str(
                    (root_path / "logs" / "vectorization_worker.log").resolve()
                )
                worker_logs_dir = str(Path(log_path).resolve().parent)

                # Get faiss_dir from storage (base directory for project-scoped indexes)
                faiss_dir = storage.faiss_dir

                # Load SVO config from config_data
                from code_analysis.core.config import ServerConfig

                svo_config = None
                code_analysis_config = config_data.get("code_analysis", {})
                if code_analysis_config:
                    try:
                        server_config = ServerConfig(**code_analysis_config)
                        svo_config = (
                            server_config.model_dump()
                            if hasattr(server_config, "model_dump")
                            else server_config.dict()
                        )
                    except Exception as e:
                        logger.warning(f"Failed to load SVO config: {e}")

                worker_manager = get_worker_manager()
                res = worker_manager.start_vectorization_worker(
                    db_path=str(db_path),
                    faiss_dir=str(faiss_dir),
                    vector_dim=vector_dim,
                    svo_config=svo_config,
                    batch_size=batch_size,
                    poll_interval=poll_interval,
                    worker_log_path=log_path,
                    worker_logs_dir=worker_logs_dir,
                )
                return SuccessResult(data=res.__dict__)

            if worker_type == "indexing":
                log_path = worker_log_path or str(
                    (root_path / "logs" / "indexing_worker.log").resolve()
                )
                worker_logs_dir = str(Path(log_path).resolve().parent)
                worker_manager = get_worker_manager()
                res = worker_manager.start_indexing_worker(
                    db_path=str(db_path),
                    poll_interval=poll_interval,
                    batch_size=batch_size,
                    worker_log_path=log_path,
                    worker_logs_dir=worker_logs_dir,
                    config_path=str(config_path) if config_path else None,
                )
                return SuccessResult(data=res.__dict__)

            return ErrorResult(
                message=f"Unsupported worker_type: {worker_type}",
                code="WORKER_START_ERROR",
                details={"worker_type": worker_type},
            )
        except Exception as e:
            return self._handle_error(e, "WORKER_START_ERROR", "start_worker")

    @classmethod
    def metadata(cls: type["StartWorkerMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The start_worker command starts a background worker process in a separate process. "
                "Supported worker types are 'file_watcher' and 'vectorization'. "
                "The worker is registered in WorkerManager and runs as a daemon process.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Loads config.json to get storage paths\n"
                "3. Opens database connection\n"
                "4. For file_watcher:\n"
                "   - Projects are discovered automatically in watch_dirs\n"
                "   - Resolves watch_dirs (defaults to [root_dir] if not provided)\n"
                "   - Starts file watcher worker process\n"
                "   - Registers worker in WorkerManager\n"
                "5. For vectorization:\n"
                "   - Gets base FAISS directory (project-scoped indexes: {faiss_dir}/{project_id}.bin)\n"
                "   - Loads SVO config for embedding service\n"
                "   - Starts universal vectorization worker process\n"
                "   - Registers worker in WorkerManager\n"
                "6. Returns worker start result with PID\n\n"
                "File Watcher Worker:\n"
                "- Monitors directories for file changes\n"
                "- Discovers projects automatically by finding projectid files\n"
                "- Scans at specified scan_interval\n"
                "- Processes new, changed, and deleted files\n"
                "- Uses lock files to prevent concurrent processing\n"
                "- Stores deleted files in version directory\n\n"
                "Vectorization Worker:\n"
                "- Processes code chunks for vectorization\n"
                "- Converts chunks to embeddings using embedding service\n"
                "- Stores vectors in FAISS index\n"
                "- Polls database at specified poll_interval\n"
                "   - Processes chunks in batches\n"
                "   - Uses project-scoped FAISS index ({faiss_dir}/{project_id}.bin)\n"
                "   - Automatically discovers all projects from database\n"
                "   - Processes projects sequentially, sorted by pending count\n\n"
                "Use cases:\n"
                "- Start file watcher to monitor project changes\n"
                "- Start vectorization worker to process code chunks\n"
                "- Run workers in background for continuous processing\n\n"
                "Important notes:\n"
                "- Workers run as daemon processes\n"
                "- Workers are registered in WorkerManager\n"
                "- File watcher discovers projects automatically\n"
                "- Vectorization worker is universal - processes all projects from database automatically\n"
                "- Vectorization worker uses project-scoped FAISS indexes (no dataset concept)\n"
                "- Workers write logs to specified log path\n"
                "- Use stop_worker to stop workers gracefully"
            ),
            "parameters": {
                "worker_type": {
                    "description": (
                        "Type of worker to start. Options: 'file_watcher', 'vectorization'. "
                        "file_watcher monitors directories for file changes. "
                        "vectorization processes code chunks for embedding."
                    ),
                    "type": "string",
                    "required": True,
                    "enum": ["file_watcher", "vectorization", "indexing"],
                },
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file and config.json. "
                        "Used to resolve storage paths (database, FAISS directory) for vectorization worker."
                    ),
                    "type": "string",
                    "required": True,
                },
                "watch_dirs": {
                    "description": (
                        "Directories to watch (file_watcher only). Defaults to [root_dir] if not provided. "
                        "Projects are discovered automatically by finding projectid files in these directories."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                },
                "scan_interval": {
                    "description": (
                        "Scan interval in seconds (file_watcher only). Default is 60. "
                        "How often the worker scans directories for changes."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 60,
                },
                "poll_interval": {
                    "description": (
                        "Poll interval in seconds (vectorization only). Default is 30. "
                        "How often the worker polls database for new chunks to process."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 30,
                },
                "batch_size": {
                    "description": (
                        "Batch size (vectorization only). Default is 10. "
                        "Number of chunks to process in each batch."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                },
                "vector_dim": {
                    "description": (
                        "Vector dimension (vectorization only). Default is 384. "
                        "Must match embedding service vector dimension."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 384,
                },
                "worker_log_path": {
                    "description": (
                        "Optional log path for worker process. "
                        "Defaults to logs/file_watcher.log or logs/vectorization_worker.log."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Start file watcher worker",
                    "command": {
                        "worker_type": "file_watcher",
                        "root_dir": "/home/user/projects/my_project",
                        "scan_interval": 60,
                    },
                    "explanation": (
                        "Starts file watcher worker that monitors root_dir for file changes. "
                        "Projects are discovered automatically."
                    ),
                },
                {
                    "description": "Start vectorization worker",
                    "command": {
                        "worker_type": "vectorization",
                        "root_dir": "/home/user/projects/my_project",
                        "poll_interval": 30,
                        "batch_size": 10,
                    },
                    "explanation": (
                        "Starts universal vectorization worker that processes code chunks for embedding. "
                        "Worker automatically discovers all projects from database and processes them sequentially."
                    ),
                },
                {
                    "description": "Start file watcher with custom watch directories",
                    "command": {
                        "worker_type": "file_watcher",
                        "root_dir": "/home/user/projects",
                        "watch_dirs": [
                            "/home/user/projects/proj1",
                            "/home/user/projects/proj2",
                        ],
                    },
                    "explanation": (
                        "Starts file watcher that monitors multiple directories. "
                        "Projects are discovered in each directory."
                    ),
                },
            ],
            "error_cases": {
                "WORKER_START_ERROR": {
                    "description": "General error during worker start",
                    "example": "Process start failure, database error, or config error",
                    "solution": (
                        "Check database integrity, verify config.json exists, "
                        "ensure embedding service is configured (for vectorization), "
                        "check file permissions."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Whether worker was started successfully",
                        "worker_type": "Type of worker that was started",
                        "pid": "Process ID of the worker process",
                        "message": "Status message",
                    },
                    "example": {
                        "success": True,
                        "worker_type": "file_watcher",
                        "pid": 12345,
                        "message": "File watcher started (PID 12345)",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., WORKER_START_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use stop_worker to stop workers gracefully before restarting",
                "File watcher discovers projects automatically - no need to specify project_id",
                "Vectorization requires embedding service to be configured",
                "Adjust scan_interval and poll_interval based on workload",
                "Monitor worker logs to ensure proper operation",
                "Workers run as daemon processes - they stop when parent process stops",
            ],
        }


class StopWorkerMCPCommand(BaseMCPCommand):
    """
    Stop background workers by type using WorkerManager.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "stop_worker"
    version = "1.0.0"
    descr = "Stop background worker(s) by type (file_watcher or vectorization)"
    category = "worker_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["StopWorkerMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Notes:
            This schema is used by MCP Proxy for request validation.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Stop background worker(s) by type.",
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization", "indexing"],
                    "description": "Type of worker to stop.",
                    "examples": ["file_watcher"],
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds before force kill.",
                    "default": 10,
                    "examples": [10],
                },
            },
            "required": ["worker_type"],
            "additionalProperties": False,
            "examples": [
                {"worker_type": "file_watcher", "timeout": 10},
                {"worker_type": "vectorization", "timeout": 10},
            ],
        }

    async def execute(
        self: "StopWorkerMCPCommand",
        worker_type: str,
        timeout: int = 10,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute stop worker command.

        Args:
            self: Command instance.
            worker_type: Worker type to stop.
            timeout: Timeout seconds.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with stop summary or ErrorResult on failure.
        """
        try:
            worker_manager = get_worker_manager()
            result = worker_manager.stop_worker_type(
                worker_type, timeout=float(timeout)
            )
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "WORKER_STOP_ERROR", "stop_worker")

    @classmethod
    def metadata(cls: type["StopWorkerMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The stop_worker command stops background worker processes by type. "
                "It stops all workers of the specified type that are registered in WorkerManager. "
                "The command attempts graceful shutdown first, then force kills if timeout is exceeded.\n\n"
                "Operation flow:\n"
                "1. Gets WorkerManager instance\n"
                "2. Retrieves all workers of specified type from registry\n"
                "3. For each worker:\n"
                "   - Attempts graceful shutdown (sends termination signal)\n"
                "   - Waits for process to terminate (up to timeout seconds)\n"
                "   - If timeout exceeded, force kills the process\n"
                "4. Unregisters workers from WorkerManager\n"
                "5. Returns stop summary with counts\n\n"
                "Shutdown Process:\n"
                "- First attempts graceful shutdown (SIGTERM)\n"
                "- Waits for process to terminate naturally\n"
                "- If timeout exceeded, force kills (SIGKILL)\n"
                "- Removes worker from registry\n\n"
                "Worker Types:\n"
                "- file_watcher: Stops all file watcher workers\n"
                "- vectorization: Stops all vectorization workers\n\n"
                "Use cases:\n"
                "- Stop workers before restarting\n"
                "- Stop workers for maintenance\n"
                "- Clean up worker processes\n\n"
                "Important notes:\n"
                "- Stops ALL workers of the specified type\n"
                "- Graceful shutdown is attempted first\n"
                "- Force kill is used if timeout exceeded\n"
                "- Workers are unregistered from WorkerManager\n"
                "- Default timeout is 10 seconds"
            ),
            "parameters": {
                "worker_type": {
                    "description": (
                        "Type of worker to stop. Options: 'file_watcher', 'vectorization'. "
                        "Stops all workers of this type that are registered."
                    ),
                    "type": "string",
                    "required": True,
                    "enum": ["file_watcher", "vectorization", "indexing"],
                },
                "timeout": {
                    "description": (
                        "Timeout in seconds before force kill. Default is 10. "
                        "If worker doesn't stop gracefully within timeout, it will be force killed."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                },
            },
            "usage_examples": [
                {
                    "description": "Stop file watcher workers",
                    "command": {
                        "worker_type": "file_watcher",
                        "timeout": 10,
                    },
                    "explanation": (
                        "Stops all file watcher workers gracefully. "
                        "Force kills if they don't stop within 10 seconds."
                    ),
                },
                {
                    "description": "Stop vectorization workers",
                    "command": {
                        "worker_type": "vectorization",
                        "timeout": 5,
                    },
                    "explanation": (
                        "Stops all vectorization workers gracefully. "
                        "Force kills if they don't stop within 5 seconds."
                    ),
                },
            ],
            "error_cases": {
                "WORKER_STOP_ERROR": {
                    "description": "General error during worker stop",
                    "example": "Process not found, permission denied, or kill failure",
                    "solution": (
                        "Check if workers are running, verify process permissions, "
                        "ensure WorkerManager is accessible."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "worker_type": "Type of workers that were stopped",
                        "stopped_count": "Number of workers stopped",
                        "failed_count": "Number of workers that failed to stop",
                        "message": "Status message",
                    },
                    "example": {
                        "worker_type": "file_watcher",
                        "stopped_count": 2,
                        "failed_count": 0,
                        "message": "Stopped 2 file_watcher worker(s)",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., WORKER_STOP_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use graceful shutdown timeout appropriate for worker workload",
                "Workers should handle SIGTERM for graceful shutdown",
                "Force kill is used as last resort if timeout exceeded",
                "Check worker status after stopping to verify shutdown",
                "Stop workers before restarting to avoid conflicts",
            ],
        }
