"""
MCP command: get_worker_status.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..worker_status import WorkerStatusCommand
from .get_worker_status_metadata import get_metadata

logger = logging.getLogger(__name__)


class GetWorkerStatusMCPCommand(BaseMCPCommand):
    """Get worker process status and activity."""

    name = "get_worker_status"
    version = "1.0.0"
    descr = "Get worker status (requires params.worker_type: file_watcher | vectorization | indexing)"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": (
                "Always pass worker_type. Calling with params {} or without worker_type is invalid "
                "and returns a validation error."
            ),
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization", "indexing"],
                    "description": (
                        "REQUIRED. Which background worker to inspect: "
                        "`file_watcher` (filesystem watcher), `vectorization` (chunk embeddings / FAISS), "
                        "or `indexing` (AST/CST/fulltext for files with needs_chunking)."
                    ),
                },
                "log_path": {
                    "type": "string",
                    "description": "Path to worker log file (optional, for activity check)",
                },
                "lock_file_path": {
                    "type": "string",
                    "description": "Path to lock file (optional, for file_watcher)",
                },
            },
            "required": ["worker_type"],
            "additionalProperties": False,
            "examples": [
                {"worker_type": "vectorization"},
                {"worker_type": "file_watcher"},
                {"worker_type": "indexing"},
            ],
        }

    async def execute(
        self,
        worker_type: str,
        log_path: Optional[str] = None,
        lock_file_path: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute get worker status command.

        Args:
            worker_type: Type of worker (file_watcher or vectorization)
            log_path: Path to worker log file
            lock_file_path: Path to lock file (for file_watcher)

        Returns:
            SuccessResult with worker status or ErrorResult on failure
        """
        try:
            if log_path is None:
                try:
                    from ...core.storage_paths import (
                        load_raw_config,
                        resolve_storage_paths,
                    )

                    config_path = self._resolve_config_path()
                    config_data = load_raw_config(config_path)
                    storage = resolve_storage_paths(
                        config_data=config_data, config_path=config_path
                    )
                    ca = config_data.get("code_analysis") or {}
                    if worker_type == "vectorization":
                        rel = (ca.get("worker") or {}).get("log_path")
                    elif worker_type == "file_watcher":
                        rel = (ca.get("file_watcher") or {}).get("log_path")
                    elif worker_type == "indexing":
                        rel = (ca.get("indexing_worker") or {}).get("log_path")
                    else:
                        rel = None
                    if rel and storage.config_dir:
                        log_path = str((storage.config_dir / rel).resolve())
                except Exception as e:
                    logger.debug("Could not resolve log_path from config: %s", e)
            command = WorkerStatusCommand(
                worker_type=worker_type,
                log_path=log_path,
                lock_file_path=lock_file_path,
            )
            result = await command.execute()

            try:
                db = self._open_database_from_config(auto_analyze=False)
                try:
                    if worker_type == "file_watcher":
                        get_fw = getattr(db, "get_file_watcher_stats", None)
                        stats = get_fw() if callable(get_fw) else None
                        if stats:
                            if stats.get("average_processing_time_seconds"):
                                avg_time = stats["average_processing_time_seconds"]
                                if avg_time and avg_time > 0:
                                    stats["processing_speed_files_per_second"] = round(
                                        1.0 / avg_time, 2
                                    )
                                else:
                                    stats["processing_speed_files_per_second"] = None
                            else:
                                stats["processing_speed_files_per_second"] = None
                            files_total = stats.get("files_total_at_start", 0)
                            files_processed = stats.get("files_processed", 0)
                            if files_total and files_total > 0:
                                stats["files_processed_percent"] = round(
                                    (files_processed / files_total) * 100, 2
                                )
                            else:
                                stats["files_processed_percent"] = None
                            result["cycle_stats"] = stats
                    elif worker_type == "vectorization":
                        get_vs = getattr(db, "get_vectorization_stats", None)
                        stats = get_vs() if callable(get_vs) else None
                        if stats:
                            if stats.get("average_processing_time_seconds"):
                                avg_time = stats["average_processing_time_seconds"]
                                if avg_time and avg_time > 0:
                                    stats["processing_speed_chunks_per_second"] = round(
                                        1.0 / avg_time, 2
                                    )
                                else:
                                    stats["processing_speed_chunks_per_second"] = None
                            else:
                                stats["processing_speed_chunks_per_second"] = None
                            result["cycle_stats"] = stats
                    elif worker_type == "indexing":
                        get_is = getattr(db, "get_indexing_stats", None)
                        stats = get_is() if callable(get_is) else None
                        if stats:
                            if stats.get("average_processing_time_seconds"):
                                avg_time = stats["average_processing_time_seconds"]
                                if avg_time and avg_time > 0:
                                    stats["processing_speed_files_per_second"] = round(
                                        1.0 / avg_time, 2
                                    )
                                else:
                                    stats["processing_speed_files_per_second"] = None
                            else:
                                stats["processing_speed_files_per_second"] = None
                            result["cycle_stats"] = stats
                finally:
                    db.disconnect()
            except Exception as e:
                logger.warning("Failed to get worker stats from database: %s", e)

            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "WORKER_STATUS_ERROR", "get_worker_status")

    @classmethod
    def metadata(cls: type["GetWorkerStatusMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_metadata(cls)
