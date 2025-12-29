"""
MCP command wrappers for starting/stopping background workers.

This module exposes simple control over background workers (file_watcher,
vectorization) via the existing WorkerManager registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.worker_launcher import (
    default_faiss_index_path,
    start_file_watcher_worker,
    start_vectorization_worker,
    stop_worker_type,
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
                "Supported worker_type values: 'file_watcher', 'vectorization'."
            ),
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization"],
                    "description": "Type of worker to start.",
                    "examples": ["file_watcher"],
                },
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db).",
                    "examples": ["/abs/path/to/project"],
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred/created by root_dir.",
                },
                "watch_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Directories to watch (file_watcher only; default: [root_dir]).",
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
                    "examples": ["/abs/path/to/logs/file_watcher.log"],
                },
            },
            "required": ["worker_type", "root_dir"],
            "additionalProperties": False,
            "examples": [
                {
                    "worker_type": "file_watcher",
                    "root_dir": "/abs/path/to/project",
                    "watch_dirs": ["/abs/path/to/project"],
                    "scan_interval": 60,
                    "worker_log_path": "/abs/path/to/project/logs/file_watcher.log",
                },
                {
                    "worker_type": "vectorization",
                    "root_dir": "/abs/path/to/project",
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
        root_dir: str,
        project_id: Optional[str] = None,
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
            root_dir: Project root directory.
            project_id: Optional project id.
            watch_dirs: Optional watch dirs for file watcher.
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
            root_path = self._validate_root_dir(root_dir)
            data_dir = root_path / "data"
            db_path = data_dir / "code_analysis.db"

            database = self._open_database(str(root_path), auto_analyze=False)
            try:
                resolved_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not resolved_project_id:
                    resolved_project_id = database.get_or_create_project(
                        str(root_path), name=root_path.name
                    )
            finally:
                database.close()

            if worker_type == "file_watcher":
                dirs = watch_dirs or [str(root_path)]
                log_path = worker_log_path or str(
                    (root_path / "logs" / "file_watcher.log").resolve()
                )
                res = start_file_watcher_worker(
                    db_path=str(db_path),
                    project_id=resolved_project_id,
                    watch_dirs=dirs,
                    scan_interval=scan_interval,
                    version_dir=str((root_path / "data" / "versions").resolve()),
                    worker_log_path=log_path,
                    project_root=str(root_path),
                    ignore_patterns=[".git", "__pycache__", "data", "logs"],
                )
                return SuccessResult(data=res.__dict__)

            if worker_type == "vectorization":
                log_path = worker_log_path or str(
                    (root_path / "logs" / "vectorization_worker.log").resolve()
                )
                res = start_vectorization_worker(
                    db_path=str(db_path),
                    project_id=resolved_project_id,
                    faiss_index_path=default_faiss_index_path(str(root_path)),
                    vector_dim=vector_dim,
                    svo_config=None,
                    batch_size=batch_size,
                    poll_interval=poll_interval,
                    worker_log_path=log_path,
                )
                return SuccessResult(data=res.__dict__)

            return ErrorResult(
                message=f"Unsupported worker_type: {worker_type}",
                code="WORKER_START_ERROR",
                details={"worker_type": worker_type},
            )
        except Exception as e:
            return self._handle_error(e, "WORKER_START_ERROR", "start_worker")


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
                    "enum": ["file_watcher", "vectorization"],
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
            result = stop_worker_type(worker_type, timeout=float(timeout))
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "WORKER_STOP_ERROR", "stop_worker")
