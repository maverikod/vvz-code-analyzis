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

        # Find worker processes
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

            from ..core.database import CodeDatabase

            db = CodeDatabase(self.db_path)

            try:
                assert db.conn is not None
                cursor = db.conn.cursor()

                # Project statistics
                cursor.execute("SELECT COUNT(*) FROM projects")
                project_count = cursor.fetchone()[0]
                cursor.execute("SELECT id, name FROM projects LIMIT 10")
                projects = cursor.fetchall()
                result["projects"] = {
                    "total": project_count,
                    "sample": [{"id": p[0], "name": p[1]} for p in projects],
                }

                # File statistics
                cursor.execute("SELECT COUNT(*) FROM files")
                total_files = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM files WHERE deleted = 1"
                )
                deleted_files = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM files WHERE has_docstring = 1")
                files_with_docstring = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM files 
                    WHERE (deleted = 0 OR deleted IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = files.id)
                    """
                )
                files_needing_chunking = cursor.fetchone()[0]

                result["files"] = {
                    "total": total_files,
                    "deleted": deleted_files,
                    "active": total_files - deleted_files,
                    "with_docstring": files_with_docstring,
                    "needing_chunking": files_needing_chunking,
                }

                # Chunk statistics
                cursor.execute("SELECT COUNT(*) FROM code_chunks")
                total_chunks = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM code_chunks WHERE embedding_vector IS NOT NULL"
                )
                vectorized_chunks = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM code_chunks WHERE embedding_vector IS NULL"
                )
                not_vectorized_chunks = cursor.fetchone()[0]

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
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM files 
                    WHERE updated_at > julianday('now', '-1 day')
                    """
                )
                files_updated_24h = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM code_chunks 
                    WHERE created_at > julianday('now', '-1 day')
                    """
                )
                chunks_updated_24h = cursor.fetchone()[0]

                result["recent_activity"] = {
                    "files_updated_24h": files_updated_24h,
                    "chunks_updated_24h": chunks_updated_24h,
                }

                # Get files needing chunking (sample)
                cursor.execute(
                    """
                    SELECT f.id, f.path, f.has_docstring, f.last_modified
                    FROM files f
                    WHERE (f.deleted = 0 OR f.deleted IS NULL)
                    AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)
                    ORDER BY f.updated_at DESC
                    LIMIT 10
                    """
                )
                files_needing_chunking_sample = cursor.fetchall()
                result["files"]["needing_chunking_sample"] = [
                    {
                        "id": f[0],
                        "path": f[1],
                        "has_docstring": bool(f[2]),
                        "last_modified": f[3],
                    }
                    for f in files_needing_chunking_sample
                ]

                # Get chunks needing vectorization (sample)
                cursor.execute(
                    """
                    SELECT id, file_id, chunk_text, created_at
                    FROM code_chunks
                    WHERE embedding_vector IS NULL
                    ORDER BY id DESC
                    LIMIT 10
                    """
                )
                chunks_needing_vectorization = cursor.fetchall()
                result["chunks"]["needing_vectorization_sample"] = [
                    {
                        "id": c[0],
                        "file_id": c[1],
                        "chunk_preview": (
                            (c[2][:100] + "...") if c[2] and len(c[2]) > 100 else c[2]
                        ),
                        "created_at": c[3],
                    }
                    for c in chunks_needing_vectorization
                ]

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error getting database status: {e}", exc_info=True)
            result["error"] = str(e)

        return result
