"""
MCP command wrappers for worker status and database monitoring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .worker_status import WorkerStatusCommand

logger = logging.getLogger(__name__)


class GetWorkerStatusMCPCommand(BaseMCPCommand):
    """Get worker process status and activity."""

    name = "get_worker_status"
    version = "1.0.0"
    descr = "Get worker process status, resource usage, and recent activity"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "worker_type": {
                    "type": "string",
                    "enum": ["file_watcher", "vectorization"],
                    "description": "Type of worker to check",
                },
                "log_path": {
                    "type": "string",
                    "description": "Path to worker log file (optional, for activity check)",
                },
                "lock_file_path": {
                    "type": "string",
                    "description": "Path to lock file (optional, for file_watcher)",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Root directory for database access (optional, for worker cycle stats)",
                },
            },
            "required": ["worker_type"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        worker_type: str,
        log_path: Optional[str] = None,
        lock_file_path: Optional[str] = None,
        root_dir: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute get worker status command.

        Args:
            worker_type: Type of worker (file_watcher or vectorization)
            log_path: Path to worker log file
            lock_file_path: Path to lock file (for file_watcher)
            root_dir: Optional root directory for database access (for worker stats)

        Returns:
            SuccessResult with worker status or ErrorResult on failure
        """
        try:
            command = WorkerStatusCommand(
                worker_type=worker_type,
                log_path=log_path,
                lock_file_path=lock_file_path,
            )
            result = await command.execute()

            # Add worker statistics from database if root_dir provided
            if root_dir:
                try:
                    db = self._open_database(root_dir, auto_analyze=False)
                    try:
                        if worker_type == "file_watcher":
                            stats = db.get_file_watcher_stats()
                            if stats:
                                # Calculate processing speed (files per second)
                                if stats.get("average_processing_time_seconds"):
                                    avg_time = stats["average_processing_time_seconds"]
                                    if avg_time and avg_time > 0:
                                        stats["processing_speed_files_per_second"] = (
                                            round(1.0 / avg_time, 2)
                                        )
                                    else:
                                        stats["processing_speed_files_per_second"] = (
                                            None
                                        )
                                else:
                                    stats["processing_speed_files_per_second"] = None
                                result["cycle_stats"] = stats
                        elif worker_type == "vectorization":
                            stats = db.get_vectorization_stats()
                            if stats:
                                # Calculate processing speed (chunks per second)
                                if stats.get("average_processing_time_seconds"):
                                    avg_time = stats["average_processing_time_seconds"]
                                    if avg_time and avg_time > 0:
                                        stats["processing_speed_chunks_per_second"] = (
                                            round(1.0 / avg_time, 2)
                                        )
                                    else:
                                        stats["processing_speed_chunks_per_second"] = (
                                            None
                                        )
                                else:
                                    stats["processing_speed_chunks_per_second"] = None
                                result["cycle_stats"] = stats
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"Failed to get worker stats from database: {e}")
                    # Don't fail the command if stats are unavailable

            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "WORKER_STATUS_ERROR", "get_worker_status")

    @classmethod
    def metadata(cls: type["GetWorkerStatusMCPCommand"]) -> Dict[str, Any]:
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
                "The get_worker_status command monitors worker process status, resource usage, "
                "and recent activity. It supports two types of workers: file_watcher and vectorization. "
                "The command provides comprehensive information about worker processes including "
                "CPU/memory usage, uptime, lock file status, and log activity.\n\n"
                "Operation flow:\n"
                "1. Validates worker_type parameter (file_watcher or vectorization)\n"
                "2. Attempts to get registered workers from WorkerManager\n"
                "3. If no registered workers, searches for processes by name pattern\n"
                "4. For file_watcher, checks lock file status if provided\n"
                "5. Reads PID from PID file if log_path provided (fallback)\n"
                "6. Collects process information (CPU, memory, uptime)\n"
                "7. Analyzes recent log activity if log_path provided\n"
                "8. Returns comprehensive status summary\n\n"
                "Worker Types:\n"
                "- file_watcher: Monitors file system changes and updates database\n"
                "- vectorization: Processes code chunks and generates embeddings\n\n"
                "Process Discovery Methods:\n"
                "1. WorkerManager: Gets registered workers (most reliable)\n"
                "2. Process name search: Searches running processes by cmdline pattern\n"
                "3. Lock file: For file_watcher, uses lock file PID\n"
                "4. PID file: Reads PID from <worker>.pid file (if log_path provided)\n\n"
                "Resource Monitoring:\n"
                "- CPU usage: Percentage of CPU time used (per process and total)\n"
                "- Memory usage: Resident Set Size (RSS) in megabytes\n"
                "- Uptime: Process uptime in seconds\n"
                "- Process status: Running state (running, sleeping, etc.)\n\n"
                "Lock File (file_watcher only):\n"
                "- Contains PID, creation timestamp, worker name, hostname\n"
                "- Used to identify active file watcher process\n"
                "- Validates that process is still alive\n\n"
                "Log Activity:\n"
                "- Analyzes recent log entries (last 10 lines by default)\n"
                "- Extracts timestamp from log entries\n"
                "- Calculates age of last entry\n"
                "- Provides file size information\n\n"
                "Use cases:\n"
                "- Monitor worker health and resource usage\n"
                "- Troubleshoot worker issues\n"
                "- Check if workers are running\n"
                "- Monitor worker performance\n"
                "- Verify worker activity from logs\n"
                "- Debug worker startup problems\n\n"
                "Important notes:\n"
                "- Requires psutil library for process information\n"
                "- Process discovery may find multiple workers of same type\n"
                "- Lock file is optional but recommended for file_watcher\n"
                "- Log path is optional but enables activity monitoring\n"
                "- PID file discovery works if log_path points to .log file"
            ),
            "parameters": {
                "worker_type": {
                    "description": (
                        "Type of worker to check. Must be one of: 'file_watcher' or 'vectorization'. "
                        "Determines which worker processes to monitor."
                    ),
                    "type": "string",
                    "required": True,
                    "enum": ["file_watcher", "vectorization"],
                    "examples": ["file_watcher", "vectorization"],
                },
                "log_path": {
                    "description": (
                        "Optional path to worker log file. If provided:\n"
                        "- Enables log activity analysis\n"
                        "- Enables PID file discovery (<log_name>.pid)\n"
                        "- Should point to worker's log file (e.g., file_watcher.log)"
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "/home/user/projects/my_project/logs/file_watcher.log",
                        "logs/vectorization.log",
                    ],
                },
                "lock_file_path": {
                    "description": (
                        "Optional path to lock file (for file_watcher only). "
                        "Lock file contains PID and metadata of active file watcher. "
                        "Used to identify the correct worker process."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "/home/user/projects/my_project/data/file_watcher.lock",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Check file watcher status",
                    "command": {
                        "worker_type": "file_watcher",
                    },
                    "explanation": (
                        "Checks status of file watcher workers. "
                        "Searches for processes and returns status information."
                    ),
                },
                {
                    "description": "Check vectorization worker with log",
                    "command": {
                        "worker_type": "vectorization",
                        "log_path": "/home/user/projects/my_project/logs/vectorization.log",
                    },
                    "explanation": (
                        "Checks vectorization worker status and analyzes log activity. "
                        "Also attempts PID file discovery from log path."
                    ),
                },
                {
                    "description": "Check file watcher with lock file",
                    "command": {
                        "worker_type": "file_watcher",
                        "lock_file_path": "/home/user/projects/my_project/data/file_watcher.lock",
                        "log_path": "/home/user/projects/my_project/logs/file_watcher.log",
                    },
                    "explanation": (
                        "Checks file watcher using lock file for process identification "
                        "and log file for activity monitoring."
                    ),
                },
            ],
            "error_cases": {
                "WORKER_STATUS_ERROR": {
                    "description": "Error during worker status check",
                    "examples": [
                        {
                            "case": "Invalid worker type",
                            "message": "Invalid worker_type",
                            "solution": "Use 'file_watcher' or 'vectorization'",
                        },
                        {
                            "case": "Permission denied",
                            "message": "Access denied to process",
                            "solution": (
                                "Check process permissions. May need elevated privileges "
                                "to access other users' processes."
                            ),
                        },
                        {
                            "case": "Log file read error",
                            "message": "Error reading log file",
                            "solution": (
                                "Verify log_path is correct and file is readable. "
                                "Error is logged but doesn't fail the command."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Worker status retrieved successfully",
                    "data": {
                        "worker_type": "Type of worker checked",
                        "timestamp": "ISO timestamp of status check",
                        "processes": (
                            "List of worker process information. Each contains:\n"
                            "- pid: Process ID\n"
                            "- status: Process status (running, sleeping, etc.)\n"
                            "- cpu_percent: CPU usage percentage\n"
                            "- memory_mb: Memory usage in megabytes\n"
                            "- create_time: Process creation timestamp\n"
                            "- uptime_seconds: Process uptime in seconds\n"
                            "- cmdline: Process command line (first 3 args)"
                        ),
                        "lock_file": (
                            "Lock file information (file_watcher only). Contains:\n"
                            "- exists: Whether lock file exists\n"
                            "- pid: PID from lock file\n"
                            "- process_alive: Whether process is still running\n"
                            "- created_at: Lock file creation timestamp\n"
                            "- worker_name: Worker name\n"
                            "- hostname: Hostname where worker runs"
                        ),
                        "log_activity": (
                            "Recent log activity information. Contains:\n"
                            "- available: Whether log file is available\n"
                            "- file_size_mb: Log file size in megabytes\n"
                            "- last_entry: Last log entry with timestamp and age\n"
                            "- recent_lines_count: Number of recent lines analyzed"
                        ),
                        "summary": {
                            "process_count": "Number of worker processes found",
                            "is_running": "True if any processes are running",
                            "total_cpu_percent": "Total CPU usage across all processes",
                            "total_memory_mb": "Total memory usage in megabytes",
                            "oldest_process_uptime_seconds": "Uptime of oldest process",
                        },
                    },
                    "example_running": {
                        "worker_type": "file_watcher",
                        "timestamp": "2024-01-15T14:30:25",
                        "processes": [
                            {
                                "pid": 12345,
                                "status": "running",
                                "cpu_percent": 2.5,
                                "memory_mb": 45.2,
                                "create_time": "2024-01-15T10:00:00",
                                "uptime_seconds": 16225,
                                "cmdline": "python -m code_analysis.workers.file_watcher",
                            }
                        ],
                        "lock_file": {
                            "exists": True,
                            "pid": 12345,
                            "process_alive": True,
                            "created_at": "2024-01-15T10:00:00",
                            "worker_name": "file_watcher",
                            "hostname": "server1",
                        },
                        "log_activity": {
                            "available": True,
                            "file_size_mb": 2.5,
                            "last_entry": {
                                "timestamp": "2024-01-15T14:29:50",
                                "age_seconds": 35,
                                "line": "2024-01-15 14:29:50 | INFO | Processed file: src/main.py",
                            },
                            "recent_lines_count": 10,
                        },
                        "summary": {
                            "process_count": 1,
                            "is_running": True,
                            "total_cpu_percent": 2.5,
                            "total_memory_mb": 45.2,
                            "oldest_process_uptime_seconds": 16225,
                        },
                    },
                    "example_not_running": {
                        "worker_type": "vectorization",
                        "timestamp": "2024-01-15T14:30:25",
                        "processes": [],
                        "lock_file": None,
                        "log_activity": {"available": False},
                        "summary": {
                            "process_count": 0,
                            "is_running": False,
                            "total_cpu_percent": 0,
                            "total_memory_mb": 0,
                        },
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., WORKER_STATUS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use log_path to enable log activity monitoring",
                "Use lock_file_path for file_watcher to get accurate process identification",
                "Check summary.is_running to quickly see if workers are active",
                "Monitor total_cpu_percent and total_memory_mb for resource usage",
                "Check log_activity.last_entry.age_seconds to verify recent activity",
                "Use process_count to detect multiple workers (may indicate issues)",
                "Check oldest_process_uptime_seconds to see worker stability",
                "If processes list is empty, worker may not be running",
            ],
        }


class GetDatabaseStatusMCPCommand(BaseMCPCommand):
    """Get database state and statistics."""

    name = "get_database_status"
    version = "1.0.0"
    descr = "Get database state, statistics, and pending work"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute get database status command.

        Args:
            root_dir: Root directory of the project

        Returns:
            SuccessResult with database status or ErrorResult on failure
        """
        try:
            from datetime import datetime

            self._validate_root_dir(root_dir)

            # Get database path from config (same way as _open_database does)
            from ..core.storage_paths import (
                load_raw_config,
                resolve_storage_paths,
                ensure_storage_dirs,
            )

            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            ensure_storage_dirs(storage)
            db_path = storage.db_path

            # Use unified database access method (not direct path construction)
            db = self._open_database(root_dir, auto_analyze=False)

            try:

                result = {
                    "db_path": str(db_path),
                    "timestamp": datetime.now().isoformat(),
                    "exists": db_path.exists() if db_path else False,
                    "file_size_mb": (
                        db_path.stat().st_size / 1024 / 1024
                        if db_path and db_path.exists()
                        else 0
                    ),
                    "projects": {},
                    "files": {},
                    "chunks": {},
                    "recent_activity": {},
                    "worker_stats": {},
                }

                # Project statistics with file and chunk counts
                project_count_row = db._fetchone(
                    "SELECT COUNT(*) as count FROM projects"
                )
                project_count = project_count_row["count"] if project_count_row else 0

                # Get projects with detailed statistics
                projects_with_stats = db._fetchall(
                    """
                    SELECT 
                        p.id,
                        p.name,
                        (SELECT COUNT(*) FROM files WHERE project_id = p.id AND (deleted = 0 OR deleted IS NULL)) as file_count,
                        (SELECT COUNT(DISTINCT f.id) 
                         FROM files f
                         WHERE f.project_id = p.id 
                         AND (f.deleted = 0 OR f.deleted IS NULL)
                         AND EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)) as chunked_files,
                        (SELECT COUNT(*) FROM code_chunks WHERE project_id = p.id) as chunk_count,
                        (SELECT COUNT(*) FROM code_chunks WHERE project_id = p.id AND vector_id IS NOT NULL) as vectorized_chunks
                    FROM projects p
                    ORDER BY p.name
                    LIMIT 10
                    """
                )

                project_list = []
                for p in projects_with_stats:
                    file_count = p["file_count"] or 0
                    chunked_files = p["chunked_files"] or 0
                    chunk_count = p["chunk_count"] or 0
                    vectorized_chunks = p["vectorized_chunks"] or 0

                    chunked_percent = (
                        round((chunked_files / file_count * 100), 2)
                        if file_count > 0
                        else 0
                    )
                    vectorized_percent = (
                        round((vectorized_chunks / chunk_count * 100), 2)
                        if chunk_count > 0
                        else 0
                    )

                    project_list.append(
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "file_count": file_count,
                            "chunked_files": chunked_files,
                            "chunked_percent": chunked_percent,
                            "chunk_count": chunk_count,
                            "vectorized_chunks": vectorized_chunks,
                            "vectorized_percent": vectorized_percent,
                        }
                    )

                result["projects"] = {
                    "total": project_count,
                    "sample": project_list,
                }

                # File statistics
                total_files_row = db._fetchone("SELECT COUNT(*) as count FROM files")
                total_files = total_files_row["count"] if total_files_row else 0

                deleted_files_row = db._fetchone(
                    "SELECT COUNT(*) as count FROM files WHERE deleted = 1"
                )
                deleted_files = deleted_files_row["count"] if deleted_files_row else 0

                files_with_docstring_row = db._fetchone(
                    "SELECT COUNT(*) as count FROM files WHERE has_docstring = 1"
                )
                files_with_docstring = (
                    files_with_docstring_row["count"] if files_with_docstring_row else 0
                )

                files_needing_chunking_row = db._fetchone(
                    """
                    SELECT COUNT(*) as count FROM files 
                    WHERE (deleted = 0 OR deleted IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = files.id)
                    """
                )
                files_needing_chunking = (
                    files_needing_chunking_row["count"]
                    if files_needing_chunking_row
                    else 0
                )

                # Files that have been chunked (have chunks)
                files_with_chunks_row = db._fetchone(
                    """
                    SELECT COUNT(DISTINCT f.id) as count FROM files f
                    WHERE (f.deleted = 0 OR f.deleted IS NULL)
                    AND EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)
                    """
                )
                files_with_chunks = (
                    files_with_chunks_row["count"] if files_with_chunks_row else 0
                )

                active_files = total_files - deleted_files
                chunked_percent = (
                    round((files_with_chunks / active_files * 100), 2)
                    if active_files > 0
                    else 0
                )

                result["files"] = {
                    "total": total_files,
                    "deleted": deleted_files,
                    "active": active_files,
                    "with_docstring": files_with_docstring,
                    "needing_chunking": files_needing_chunking,
                    "chunked": files_with_chunks,
                    "chunked_percent": chunked_percent,
                }

                # Chunk statistics - use vector_id (not embedding_vector) for consistency
                total_chunks_row = db._fetchone(
                    "SELECT COUNT(*) as count FROM code_chunks"
                )
                total_chunks = total_chunks_row["count"] if total_chunks_row else 0

                vectorized_chunks_row = db._fetchone(
                    "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NOT NULL"
                )
                vectorized_chunks = (
                    vectorized_chunks_row["count"] if vectorized_chunks_row else 0
                )

                not_vectorized_chunks_row = db._fetchone(
                    "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NULL"
                )
                not_vectorized_chunks = (
                    not_vectorized_chunks_row["count"]
                    if not_vectorized_chunks_row
                    else 0
                )

                vectorization_percent = (
                    round((vectorized_chunks / total_chunks * 100), 2)
                    if total_chunks > 0
                    else 0
                )

                result["chunks"] = {
                    "total": total_chunks,
                    "vectorized": vectorized_chunks,
                    "not_vectorized": not_vectorized_chunks,
                    "vectorization_percent": vectorization_percent,
                }

                # Recent activity (last 24 hours)
                files_updated_24h_row = db._fetchone(
                    """
                    SELECT COUNT(*) as count FROM files 
                    WHERE updated_at > julianday('now', '-1 day')
                    """
                )
                files_updated_24h = (
                    files_updated_24h_row["count"] if files_updated_24h_row else 0
                )

                chunks_updated_24h_row = db._fetchone(
                    """
                    SELECT COUNT(*) as count FROM code_chunks 
                    WHERE created_at > julianday('now', '-1 day')
                    """
                )
                chunks_updated_24h = (
                    chunks_updated_24h_row["count"] if chunks_updated_24h_row else 0
                )

                result["recent_activity"] = {
                    "files_updated_24h": files_updated_24h,
                    "chunks_updated_24h": chunks_updated_24h,
                }

                # Get worker statistics
                file_watcher_stats = db.get_file_watcher_stats()
                vectorization_stats = db.get_vectorization_stats()

                # Calculate processing speed (files/chunks per second) from average time
                if file_watcher_stats and file_watcher_stats.get(
                    "average_processing_time_seconds"
                ):
                    avg_time = file_watcher_stats["average_processing_time_seconds"]
                    if avg_time and avg_time > 0:
                        file_watcher_stats["processing_speed_files_per_second"] = round(
                            1.0 / avg_time, 2
                        )
                    else:
                        file_watcher_stats["processing_speed_files_per_second"] = None
                else:
                    if file_watcher_stats:
                        file_watcher_stats["processing_speed_files_per_second"] = None

                if vectorization_stats and vectorization_stats.get(
                    "average_processing_time_seconds"
                ):
                    avg_time = vectorization_stats["average_processing_time_seconds"]
                    if avg_time and avg_time > 0:
                        vectorization_stats["processing_speed_chunks_per_second"] = (
                            round(1.0 / avg_time, 2)
                        )
                    else:
                        vectorization_stats["processing_speed_chunks_per_second"] = None
                else:
                    if vectorization_stats:
                        vectorization_stats["processing_speed_chunks_per_second"] = None

                result["worker_stats"] = {
                    "file_watcher": file_watcher_stats,
                    "vectorization": vectorization_stats,
                }

                # Get files needing chunking (sample)
                files_needing_chunking_sample = db._fetchall(
                    """
                    SELECT f.id, f.path, f.has_docstring, f.last_modified
                    FROM files f
                    WHERE (f.deleted = 0 OR f.deleted IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)
                    ORDER BY f.updated_at DESC
                    LIMIT 10
                    """
                )
                result["files"]["needing_chunking_sample"] = [
                    {
                        "id": f["id"],
                        "path": f["path"],
                        "has_docstring": bool(f["has_docstring"]),
                        "last_modified": f["last_modified"],
                    }
                    for f in files_needing_chunking_sample
                ]

                # Get chunks needing vectorization (sample) - use vector_id
                chunks_needing_vectorization = db._fetchall(
                    """
                    SELECT id, file_id, chunk_text, created_at
                    FROM code_chunks
                    WHERE vector_id IS NULL
                    ORDER BY id DESC
                    LIMIT 10
                    """
                )
                result["chunks"]["needing_vectorization_sample"] = [
                    {
                        "id": c["id"],
                        "file_id": c["file_id"],
                        "chunk_preview": (
                            (c["chunk_text"][:100] + "...")
                            if c["chunk_text"] and len(c["chunk_text"]) > 100
                            else c["chunk_text"]
                        ),
                        "created_at": c["created_at"],
                    }
                    for c in chunks_needing_vectorization
                ]

                return SuccessResult(data=result)
            finally:
                db.close()
        except Exception as e:
            return self._handle_error(e, "DATABASE_STATUS_ERROR", "get_database_status")

    @classmethod
    def metadata(cls: type["GetDatabaseStatusMCPCommand"]) -> Dict[str, Any]:
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
                "The get_database_status command provides comprehensive monitoring of the "
                "SQLite database state, statistics, and pending work. It reports file statistics, "
                "chunk statistics, project information, and recent activity to help monitor "
                "database health and identify work that needs to be done.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Resolves database path: root_dir/data/code_analysis.db\n"
                "3. Checks if database file exists\n"
                "4. Gets file size if database exists\n"
                "5. Opens database connection\n"
                "6. Queries project statistics\n"
                "7. Queries file statistics (total, deleted, with docstrings, needing chunking)\n"
                "8. Queries chunk statistics (total, vectorized, not vectorized)\n"
                "9. Queries recent activity (last 24 hours)\n"
                "10. Gets samples of files needing chunking\n"
                "11. Gets samples of chunks needing vectorization\n"
                "12. Returns comprehensive status report\n\n"
                "File Statistics:\n"
                "- total: Total number of files in database\n"
                "- deleted: Number of deleted files\n"
                "- active: Number of active (non-deleted) files\n"
                "- with_docstring: Files that have docstrings\n"
                "- needing_chunking: Active files without chunks\n"
                "- needing_chunking_sample: Sample of files needing chunking (up to 10)\n\n"
                "Chunk Statistics:\n"
                "- total: Total number of code chunks\n"
                "- vectorized: Chunks with embedding vectors\n"
                "- not_vectorized: Chunks without embedding vectors\n"
                "- vectorization_percent: Percentage of chunks that are vectorized\n"
                "- needing_vectorization_sample: Sample of chunks needing vectorization (up to 10)\n\n"
                "Project Statistics:\n"
                "- total: Total number of projects\n"
                "- sample: Sample of projects (up to 10) with id and name\n\n"
                "Recent Activity:\n"
                "- files_updated_24h: Files updated in last 24 hours\n"
                "- chunks_updated_24h: Chunks created in last 24 hours\n\n"
                "Use cases:\n"
                "- Monitor database health and size\n"
                "- Check pending work (files needing chunking, chunks needing vectorization)\n"
                "- Track project and file statistics\n"
                "- Monitor recent activity\n"
                "- Identify files that need processing\n"
                "- Verify vectorization progress\n"
                "- Database capacity planning\n\n"
                "Important notes:\n"
                "- Database must exist (returns error if not found)\n"
                "- Statistics are calculated from database queries\n"
                "- Samples are limited to 10 items each\n"
                "- Recent activity uses SQLite julianday() for time calculations\n"
                "- File size is reported in megabytes\n"
                "- All statistics are read-only (no database modifications)"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        ".",
                        "./code_analysis",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Check database status",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns comprehensive database statistics including files, chunks, "
                        "projects, and recent activity."
                    ),
                },
                {
                    "description": "Monitor database health",
                    "command": {
                        "root_dir": ".",
                    },
                    "explanation": (
                        "Checks database status in current directory to monitor health and pending work."
                    ),
                },
            ],
            "error_cases": {
                "DATABASE_STATUS_ERROR": {
                    "description": "Error during database status check",
                    "examples": [
                        {
                            "case": "Database file not found",
                            "message": "Database file not found",
                            "solution": (
                                "Verify root_dir is correct and database exists. "
                                "Run update_indexes to create database if needed."
                            ),
                        },
                        {
                            "case": "Database connection error",
                            "message": "Error connecting to database",
                            "solution": (
                                "Check database file permissions. "
                                "Verify database is not corrupted (use get_database_corruption_status)."
                            ),
                        },
                        {
                            "case": "Query error",
                            "message": "Error executing query",
                            "solution": (
                                "Database schema may be outdated. "
                                "Check database integrity and consider repair if needed."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Database status retrieved successfully",
                    "data": {
                        "db_path": "Path to database file",
                        "timestamp": "ISO timestamp of status check",
                        "exists": "True if database file exists",
                        "file_size_mb": "Database file size in megabytes",
                        "projects": {
                            "total": "Total number of projects",
                            "sample": "List of project samples (up to 10) with id and name",
                        },
                        "files": {
                            "total": "Total number of files",
                            "deleted": "Number of deleted files",
                            "active": "Number of active (non-deleted) files",
                            "with_docstring": "Files with docstrings",
                            "needing_chunking": "Active files without chunks",
                            "needing_chunking_sample": (
                                "Sample of files needing chunking (up to 10). "
                                "Each contains: id, path, has_docstring, last_modified"
                            ),
                        },
                        "chunks": {
                            "total": "Total number of chunks",
                            "vectorized": "Chunks with embedding vectors",
                            "not_vectorized": "Chunks without embedding vectors",
                            "vectorization_percent": "Percentage of vectorized chunks",
                            "needing_vectorization_sample": (
                                "Sample of chunks needing vectorization (up to 10). "
                                "Each contains: id, file_id, chunk_preview, created_at"
                            ),
                        },
                        "recent_activity": {
                            "files_updated_24h": "Files updated in last 24 hours",
                            "chunks_updated_24h": "Chunks created in last 24 hours",
                        },
                        "error": "Error message if status check failed (optional)",
                    },
                    "example": {
                        "db_path": "/home/user/projects/my_project/data/code_analysis.db",
                        "timestamp": "2024-01-15T14:30:25",
                        "exists": True,
                        "file_size_mb": 125.5,
                        "projects": {
                            "total": 3,
                            "sample": [
                                {
                                    "id": "123e4567-e89b-12d3-a456-426614174000",
                                    "name": "project1",
                                },
                                {
                                    "id": "223e4567-e89b-12d3-a456-426614174001",
                                    "name": "project2",
                                },
                            ],
                        },
                        "files": {
                            "total": 1500,
                            "deleted": 50,
                            "active": 1450,
                            "with_docstring": 1200,
                            "needing_chunking": 25,
                            "needing_chunking_sample": [
                                {
                                    "id": 1001,
                                    "path": "src/new_file.py",
                                    "has_docstring": False,
                                    "last_modified": "2024-01-15T10:00:00",
                                }
                            ],
                        },
                        "chunks": {
                            "total": 5000,
                            "vectorized": 4800,
                            "not_vectorized": 200,
                            "vectorization_percent": 96.0,
                            "needing_vectorization_sample": [
                                {
                                    "id": 5001,
                                    "file_id": 1001,
                                    "chunk_preview": "def new_function(): ...",
                                    "created_at": "2024-01-15T10:00:00",
                                }
                            ],
                        },
                        "recent_activity": {
                            "files_updated_24h": 45,
                            "chunks_updated_24h": 120,
                        },
                    },
                    "example_not_found": {
                        "db_path": "/home/user/projects/my_project/data/code_analysis.db",
                        "timestamp": "2024-01-15T14:30:25",
                        "exists": False,
                        "file_size_mb": 0,
                        "error": "Database file not found",
                        "projects": {},
                        "files": {},
                        "chunks": {},
                        "recent_activity": {},
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., DATABASE_STATUS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Check exists field first to verify database exists",
                "Monitor file_size_mb to track database growth",
                "Check files.needing_chunking to identify pending work",
                "Check chunks.not_vectorized to see vectorization backlog",
                "Use vectorization_percent to track vectorization progress",
                "Review needing_chunking_sample to see specific files needing processing",
                "Review needing_vectorization_sample to see specific chunks needing vectorization",
                "Monitor recent_activity to see database update frequency",
                "Use this command regularly to monitor database health",
                "Check projects.total to verify project registration",
            ],
        }
