"""
Internal commands for monitoring worker status and database state.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import psutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkerStatusCommand:
    """
    Command to check worker process status.

    Checks:
    - Process existence and PID
    - CPU and memory usage
    - Process uptime
    - Lock file status (for file watcher)
    - Recent log activity
    """

    def __init__(
        self,
        worker_type: str,  # "file_watcher" or "vectorization"
        log_path: Optional[str] = None,
        lock_file_path: Optional[str] = None,  # For file watcher
    ):
        """
        Initialize worker status command.

        Args:
            worker_type: Type of worker ("file_watcher" or "vectorization")
            log_path: Path to worker log file (optional)
            lock_file_path: Path to lock file for file watcher (optional)
        """
        self.worker_type = worker_type
        self.log_path = Path(log_path) if log_path else None
        self.lock_file_path = Path(lock_file_path) if lock_file_path else None

    def _get_pid_file_path(self) -> Optional[Path]:
        """
        Get PID file path for the worker based on the log file path.

        This project starts workers as `multiprocessing.Process(daemon=True)`. With the
        "spawn" start method, the OS process cmdline often does not contain
        "vectorization"/"file_watcher", so heuristic cmdline search is unreliable.

        We therefore also support PID file discovery: if `log_path` is provided and
        points to `<name>.log`, a sibling `<name>.pid` is used.

        Returns:
            PID file path if `log_path` exists and has a `.log` suffix, otherwise None.
        """
        if not self.log_path:
            return None
        if self.log_path.suffix != ".log":
            return None
        return self.log_path.with_suffix(".pid")

    def _get_lock_file_info(self) -> Optional[Dict[str, Any]]:
        """Get lock file information for file watcher."""
        if not self.lock_file_path or not self.lock_file_path.exists():
            return None

        try:
            import json

            with open(self.lock_file_path, "r") as f:
                lock_data = json.load(f)

            pid = lock_data.get("pid")
            is_alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    is_alive = True
                except (OSError, ProcessLookupError):
                    is_alive = False

            return {
                "exists": True,
                "pid": pid,
                "process_alive": is_alive,
                "created_at": lock_data.get("created_at"),
                "worker_name": lock_data.get("worker_name"),
                "hostname": lock_data.get("hostname"),
            }
        except Exception as e:
            logger.warning(f"Error reading lock file: {e}")
            return {"exists": True, "error": str(e)}

    def _get_process_by_pid(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get process information by PID."""
        try:
            process = psutil.Process(pid)
            return {
                "pid": pid,
                "status": process.status(),
                "cpu_percent": process.cpu_percent(interval=0.1),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "create_time": datetime.fromtimestamp(
                    process.create_time()
                ).isoformat(),
                "uptime_seconds": int(
                    datetime.now().timestamp() - process.create_time()
                ),
                "cmdline": " ".join(process.cmdline()[:3]),  # First 3 args
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def _find_worker_processes(self) -> List[Dict[str, Any]]:
        """Find worker processes by name pattern."""
        processes = []
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
                try:
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if self.worker_type == "file_watcher":
                        if (
                            "file_watcher" in cmdline.lower()
                            or "run_file_watcher_worker" in cmdline
                        ):
                            processes.append(proc.info)
                    elif self.worker_type == "vectorization":
                        if (
                            "vectorization" in cmdline.lower()
                            or "run_vectorization_worker" in cmdline
                        ):
                            processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.warning(f"Error finding processes: {e}")
        return processes

    def _get_pid_from_pid_file(self) -> Optional[int]:
        """
        Read PID from `<worker>.pid` file if available.

        Returns:
            PID if pid file exists and contains a valid integer, otherwise None.
        """
        pid_file = self._get_pid_file_path()
        if not pid_file or not pid_file.exists():
            return None

        try:
            content = pid_file.read_text(encoding="utf-8").strip()
            return int(content)
        except Exception:
            return None

    def _get_recent_log_activity(self, lines: int = 10) -> Dict[str, Any]:
        """Get recent log activity."""
        if not self.log_path or not self.log_path.exists():
            return {"available": False}

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                # Read last N lines
                all_lines = f.readlines()
                recent_lines = (
                    all_lines[-lines:] if len(all_lines) > lines else all_lines
                )

            # Parse last entry
            last_entry = None
            if recent_lines:
                last_line = recent_lines[-1].strip()
                # Try to extract timestamp
                timestamp_match = None
                for line in reversed(recent_lines):
                    match = None
                    # Try structured format
                    parts = line.split(" | ", 2)
                    if len(parts) == 3:
                        try:
                            timestamp_match = datetime.strptime(
                                parts[0].strip(), "%Y-%m-%d %H:%M:%S"
                            )
                            break
                        except ValueError:
                            pass
                    # Try alternative format
                    match = None
                    if not match:
                        match = None
                        parts = line.split(" - ", 2)
                        if len(parts) >= 2:
                            try:
                                timestamp_match = datetime.strptime(
                                    parts[0].strip(), "%Y-%m-%d %H:%M:%S"
                                )
                                break
                            except ValueError:
                                pass

                if timestamp_match:
                    last_entry = {
                        "timestamp": timestamp_match.isoformat(),
                        "age_seconds": int(
                            (datetime.now() - timestamp_match).total_seconds()
                        ),
                        "line": last_line[:200],  # First 200 chars
                    }

            return {
                "available": True,
                "file_size_mb": self.log_path.stat().st_size / 1024 / 1024,
                "last_entry": last_entry,
                "recent_lines_count": len(recent_lines),
            }
        except Exception as e:
            logger.warning(f"Error reading log file: {e}")
            return {"available": True, "error": str(e)}

    async def execute(self) -> Dict[str, Any]:
        """
        Execute worker status command.

        Returns:
            Dictionary with worker status information
        """
        result = {
            "worker_type": self.worker_type,
            "timestamp": datetime.now().isoformat(),
            "processes": [],
            "lock_file": None,
            "log_activity": None,
        }

        # First, try to get registered workers from WorkerManager
        try:
            from ..core.worker_manager import get_worker_manager

            worker_manager = get_worker_manager()
            manager_status = worker_manager.get_worker_status()

            # Get workers of this type from manager
            workers_by_type = manager_status.get("by_type", {}).get(
                self.worker_type, {}
            )
            registered_pids = workers_by_type.get("pids", [])

            # Get process details for registered workers
            for pid in registered_pids:
                if pid:
                    proc_details = self._get_process_by_pid(pid)
                    if proc_details:
                        result["processes"].append(proc_details)
        except Exception as e:
            logger.warning(f"Failed to get workers from WorkerManager: {e}")

        # If no registered workers found, try to find by process name
        if not result["processes"]:
            processes = self._find_worker_processes()
            for proc_info in processes:
                pid = proc_info.get("pid")
                if pid:
                    proc_details = self._get_process_by_pid(pid)
                    if proc_details:
                        result["processes"].append(proc_details)

        # Get lock file info (for file watcher)
        if self.worker_type == "file_watcher":
            result["lock_file"] = self._get_lock_file_info()

            # Use lock pid as a strong signal of the active worker process.
            lock_pid = None
            if isinstance(result["lock_file"], dict):
                lock_pid = result["lock_file"].get("pid")
            if isinstance(lock_pid, int):
                proc_details = self._get_process_by_pid(lock_pid)
                if proc_details:
                    existing_pids = {p.get("pid") for p in result["processes"]}
                    if lock_pid not in existing_pids:
                        result["processes"].append(proc_details)

        # Fallback: PID file discovery (vectorization/file_watcher)
        if not result["processes"]:
            pid = self._get_pid_from_pid_file()
            if isinstance(pid, int):
                proc_details = self._get_process_by_pid(pid)
                if proc_details:
                    result["processes"].append(proc_details)

        # Get recent log activity
        result["log_activity"] = self._get_recent_log_activity()

        # Summary
        result["summary"] = {
            "process_count": len(result["processes"]),
            "is_running": len(result["processes"]) > 0,
            "total_cpu_percent": sum(
                p.get("cpu_percent", 0) for p in result["processes"]
            ),
            "total_memory_mb": sum(p.get("memory_mb", 0) for p in result["processes"]),
        }

        if result["processes"]:
            oldest_process = min(
                result["processes"], key=lambda p: p.get("create_time", "")
            )
            result["summary"]["oldest_process_uptime_seconds"] = oldest_process.get(
                "uptime_seconds", 0
            )

        return result


class DatabaseStatusCommand:
    """
    Command to check database state.

    Provides:
    - File statistics (total, with docstrings, deleted, etc.)
    - Chunk statistics (total, vectorized, not vectorized)
    - Project statistics
    - Recent activity
    """

    def __init__(self, db_path: str):
        """
        Initialize database status command.

        Args:
            db_path: Path to database file
        """
        self.db_path = Path(db_path)

    async def execute(self) -> Dict[str, Any]:
        """
        Execute database status command.

        Returns:
            Dictionary with database statistics
        """
        result = {
            "db_path": str(self.db_path),
            "timestamp": datetime.now().isoformat(),
            "exists": self.db_path.exists(),
            "file_size_mb": 0,
            "projects": {},
            "files": {},
            "chunks": {},
            "recent_activity": {},
        }

        if not self.db_path.exists():
            result["error"] = "Database file not found"
            return result

        try:
            result["file_size_mb"] = self.db_path.stat().st_size / 1024 / 1024

            from ..core.database_client.client import DatabaseClient
            from ..core.constants import DEFAULT_DB_DRIVER_SOCKET_DIR

            # Get socket path for database driver
            db_name = self.db_path.stem
            socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
            socket_dir.mkdir(parents=True, exist_ok=True)
            socket_path = str(socket_dir / f"{db_name}_driver.sock")
            db = DatabaseClient(socket_path=socket_path)
            db.connect()

            try:
                # Project statistics
                result_data = db.execute("SELECT COUNT(*) as count FROM projects")
                data = result_data.get("data", [])
                project_count = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute("SELECT id, name FROM projects LIMIT 10")
                projects = result_data.get("data", [])
                result["projects"] = {
                    "total": project_count,
                    "sample": [{"id": p["id"], "name": p["name"]} for p in projects],
                }

                # File statistics
                result_data = db.execute("SELECT COUNT(*) as count FROM files")
                data = result_data.get("data", [])
                total_files = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute(
                    "SELECT COUNT(*) as count FROM files WHERE deleted = 1"
                )
                data = result_data.get("data", [])
                deleted_files = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute(
                    "SELECT COUNT(*) as count FROM files WHERE has_docstring = 1"
                )
                data = result_data.get("data", [])
                files_with_docstring = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute(
                    """
                    SELECT COUNT(*) as count FROM files 
                    WHERE (deleted = 0 OR deleted IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = files.id)
                    """
                )
                data = result_data.get("data", [])
                files_needing_chunking = (
                    data[0]["count"] if data and len(data) > 0 else 0
                )

                result["files"] = {
                    "total": total_files,
                    "deleted": deleted_files,
                    "active": total_files - deleted_files,
                    "with_docstring": files_with_docstring,
                    "needing_chunking": files_needing_chunking,
                }

                # Chunk statistics
                result_data = db.execute("SELECT COUNT(*) as count FROM code_chunks")
                data = result_data.get("data", [])
                total_chunks = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute(
                    "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_vector IS NOT NULL"
                )
                data = result_data.get("data", [])
                vectorized_chunks = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute(
                    "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_vector IS NULL"
                )
                data = result_data.get("data", [])
                not_vectorized_chunks = (
                    data[0]["count"] if data and len(data) > 0 else 0
                )

                result["chunks"] = {
                    "total": total_chunks,
                    "vectorized": vectorized_chunks,
                    "not_vectorized": not_vectorized_chunks,
                    "vectorization_percent": (
                        (vectorized_chunks / total_chunks * 100)
                        if total_chunks > 0
                        else 0
                    ),
                }

                # Recent activity (last 24 hours)
                result_data = db.execute(
                    """
                    SELECT COUNT(*) as count FROM files 
                    WHERE updated_at > julianday('now', '-1 day')
                    """
                )
                data = result_data.get("data", [])
                files_updated_24h = data[0]["count"] if data and len(data) > 0 else 0

                result_data = db.execute(
                    """
                    SELECT COUNT(*) as count FROM code_chunks 
                    WHERE created_at > julianday('now', '-1 day')
                    """
                )
                data = result_data.get("data", [])
                chunks_updated_24h = data[0]["count"] if data and len(data) > 0 else 0

                result["recent_activity"] = {
                    "files_updated_24h": files_updated_24h,
                    "chunks_updated_24h": chunks_updated_24h,
                }

                # Get files needing chunking (sample)
                result_data = db.execute(
                    """
                    SELECT f.id, f.path, f.has_docstring, f.last_modified
                    FROM files f
                    WHERE (f.deleted = 0 OR f.deleted IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)
                    ORDER BY f.updated_at DESC
                    LIMIT 10
                    """
                )
                files_needing_chunking_sample = result_data.get("data", [])
                result["files"]["needing_chunking_sample"] = [
                    {
                        "id": f["id"],
                        "path": f["path"],
                        "has_docstring": bool(f["has_docstring"]),
                        "last_modified": f["last_modified"],
                    }
                    for f in files_needing_chunking_sample
                ]

                # Get chunks needing vectorization (sample)
                result_data = db.execute(
                    """
                    SELECT id, file_id, chunk_text, created_at
                    FROM code_chunks
                    WHERE embedding_vector IS NULL
                    ORDER BY id DESC
                    LIMIT 10
                    """
                )
                chunks_needing_vectorization = result_data.get("data", [])
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

            finally:
                db.disconnect()

        except Exception as e:
            logger.error(f"Error getting database status: {e}", exc_info=True)
            result["error"] = str(e)

        return result
