"""
MCP command: start_worker — start background worker (file_watcher, vectorization, indexing).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.worker_manager import get_worker_manager
from ..core.storage_paths import load_raw_config
from ..core.worker_start_args import (
    resolve_file_watcher_worker_kwargs,
    resolve_indexing_worker_kwargs,
    resolve_vectorization_worker_kwargs,
)


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
                    "description": (
                        "Directories to watch (file_watcher only). Omit to default "
                        "to a single watch directory at the project root resolved "
                        "from project_id."
                    ),
                    "examples": [["/abs/path/to/project"]],
                },
                "scan_interval": {
                    "type": "integer",
                    "description": (
                        "Scan interval seconds (file_watcher only). Omit to use "
                        "code_analysis.file_watcher.scan_interval from server config "
                        "(defaults to 60 there)."
                    ),
                    "examples": [60],
                },
                "poll_interval": {
                    "type": "integer",
                    "description": (
                        "Poll interval seconds (vectorization only; ignored for "
                        "indexing, which always polls via its own worker loop). "
                        "Omit to use code_analysis.worker.poll_interval from "
                        "server config."
                    ),
                    "examples": [30],
                },
                "batch_size": {
                    "type": "integer",
                    "description": (
                        "Batch size (vectorization or indexing; ignored for "
                        "file_watcher). Omit to use the configured value for the "
                        "given worker_type (code_analysis.worker.batch_size for "
                        "vectorization, code_analysis.indexing_worker.batch_size "
                        "for indexing)."
                    ),
                    "examples": [5, 10],
                },
                "vector_dim": {
                    "type": "integer",
                    "description": (
                        "Vector dimension (vectorization only). Omit to use "
                        "code_analysis.vector_dim from server config (must match "
                        "the embedding service vector dimension)."
                    ),
                    "examples": [384],
                },
                "worker_log_path": {
                    "type": "string",
                    "description": (
                        "Optional log path for the worker process. Omit to use the "
                        "server-configured log path (falls back to server.log_dir "
                        "when unset), matching where the server itself would start "
                        "this worker type at boot."
                    ),
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
                    "batch_size": 5,
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
        scan_interval: Optional[int] = None,
        poll_interval: Optional[int] = None,
        batch_size: Optional[int] = None,
        vector_dim: Optional[int] = None,
        worker_log_path: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute start worker command.

        Resolves start kwargs through ``code_analysis.core.worker_start_args``
        -- the same boot-parity resolvers ``main_workers.py`` uses at server
        startup -- so a manually-started worker lands on the same config-driven
        log path, batch/poll settings, and enabled kill-switch as one started
        automatically (bug 827e2b05: this command used to build its own,
        divergent kwargs). Only parameters the caller actually passed are
        applied as overrides; everything else comes from server config.
        """
        try:
            root_path = self._resolve_project_root(project_id)
            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)

            if worker_type == "file_watcher":
                overrides: Dict[str, Any] = {
                    "watch_dirs": [
                        {"path": d, "id": d} for d in (watch_dirs or [str(root_path)])
                    ],
                }
                if scan_interval is not None:
                    overrides["scan_interval"] = scan_interval
                if worker_log_path is not None:
                    overrides["worker_log_path"] = worker_log_path
                plan = resolve_file_watcher_worker_kwargs(
                    config_data, config_path, overrides=overrides
                )
                if not plan.ok:
                    return ErrorResult(
                        message=plan.skip_reason or "file_watcher worker not started",
                        code="WORKER_START_SKIPPED",
                        details={"worker_type": worker_type},
                    )
                worker_manager = get_worker_manager()
                res = worker_manager.start_file_watcher_worker(**plan.kwargs)
                return SuccessResult(data=res.__dict__)

            if worker_type == "vectorization":
                overrides = {}
                if vector_dim is not None:
                    overrides["vector_dim"] = vector_dim
                if batch_size is not None:
                    overrides["batch_size"] = batch_size
                if poll_interval is not None:
                    overrides["poll_interval"] = poll_interval
                if worker_log_path is not None:
                    overrides["worker_log_path"] = worker_log_path
                plan = resolve_vectorization_worker_kwargs(
                    config_data, config_path, overrides=overrides
                )
                if not plan.ok:
                    return ErrorResult(
                        message=plan.skip_reason or "vectorization worker not started",
                        code="WORKER_START_SKIPPED",
                        details={"worker_type": worker_type},
                    )
                worker_manager = get_worker_manager()
                res = worker_manager.start_vectorization_worker(**plan.kwargs)
                return SuccessResult(data=res.__dict__)

            if worker_type == "indexing":
                overrides = {}
                if batch_size is not None:
                    overrides["batch_size"] = batch_size
                if poll_interval is not None:
                    overrides["poll_interval"] = poll_interval
                if worker_log_path is not None:
                    overrides["worker_log_path"] = worker_log_path
                plan = resolve_indexing_worker_kwargs(
                    config_data, config_path, overrides=overrides
                )
                if not plan.ok:
                    return ErrorResult(
                        message=plan.skip_reason or "indexing worker not started",
                        code="WORKER_START_SKIPPED",
                        details={"worker_type": worker_type},
                    )
                worker_manager = get_worker_manager()
                res = worker_manager.start_indexing_worker(**plan.kwargs)
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
