"""
MCP command: start_worker — start background worker (file_watcher, vectorization, indexing).

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
from ..core.storage_paths import load_raw_config, resolve_storage_paths

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
        """Get JSON schema for command parameters."""
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
        """Execute start worker command."""
        try:
            root_path = self._resolve_project_root(project_id)
            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path

            if worker_type == "file_watcher":
                dirs = watch_dirs or [str(root_path)]
                watch_dirs_config = [{"path": d, "id": d} for d in dirs]
                log_path = worker_log_path or str(
                    (root_path / "logs" / "file_watcher.log").resolve()
                )
                worker_logs_dir = str(Path(log_path).resolve().parent)
                worker_manager = get_worker_manager()
                res = worker_manager.start_file_watcher_worker(
                    db_path=str(db_path),
                    watch_dirs=watch_dirs_config,
                    config_path=str(config_path),
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
                faiss_dir = storage.faiss_dir
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
                        logger.warning("Failed to load SVO config: %s", e)

                worker_manager = get_worker_manager()
                res = worker_manager.start_vectorization_worker(
                    db_path=str(db_path),
                    faiss_dir=str(faiss_dir),
                    config_path=str(config_path),
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
                code_analysis_cfg = config_data.get("code_analysis", {}) or {}
                worker_cfg = code_analysis_cfg.get("worker", {}) or {}
                log_timing = bool(worker_cfg.get("log_all_operations_timing", False))
                worker_manager = get_worker_manager()
                res = worker_manager.start_indexing_worker(
                    db_path=str(db_path),
                    config_path=str(config_path),
                    poll_interval=poll_interval,
                    batch_size=batch_size,
                    worker_log_path=log_path,
                    worker_logs_dir=worker_logs_dir,
                    log_timing=log_timing,
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
        """Get detailed command metadata for AI models."""
        from .worker_management_mcp_commands_schema import get_start_worker_metadata

        return get_start_worker_metadata(
            cls.name,
            cls.version,
            cls.descr,
            cls.category,
            cls.author,
            cls.email,
        )
