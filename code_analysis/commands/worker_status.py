"""
Internal commands for monitoring worker status.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import os
import psutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.worker_status_file import read_worker_status

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

    def _get_status_file_path(self) -> Optional[Path]:
        """
        Get worker status file path (current_operation, current_file) from log path.

        Convention: same directory as log, same base name, .status.json suffix.
        E.g. logs/vectorization_worker.log -> logs/vectorization_worker.status.json.
        """
        if not self.log_path:
            return None
        if self.log_path.suffix != ".log":
            return None
        return self.log_path.with_suffix(".status.json")

    def _get_worker_progress(self) -> Optional[Dict[str, Any]]:
        """Read current_operation and current_file from worker status file."""
        status_path = self._get_status_file_path()
        return read_worker_status(status_path)

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

    def _get_pid_files_to_verify(self) -> List[Path]:
        """
        Return PID file paths to verify against the registry for current worker_type.

        Returns:
            List of PID file paths (may not exist).
        """
        from ..core.constants import LOGS_DIR_NAME

        if self.worker_type == "all":
            logs_dir = Path(LOGS_DIR_NAME).resolve()
            return [
                logs_dir / "vectorization_worker.pid",
                logs_dir / "file_watcher_worker.pid",
                logs_dir / "indexing_worker.pid",
            ]
        pid_path = self._get_pid_file_path()
        return [pid_path] if pid_path else []

    def _verify_pid_files_against_registry(self, registered_pids: set[int]) -> None:
        """
        If a PID file exists and the process in it is alive but not in the registry,
        log an error (worker running but not registered).
        """
        for pid_file in self._get_pid_files_to_verify():
            if not pid_file or not pid_file.exists():
                continue
            try:
                content = pid_file.read_text(encoding="utf-8").strip()
                pid = int(content)
            except (ValueError, OSError):
                continue
            try:
                os.kill(pid, 0)
            except OSError:
                continue
            if pid not in registered_pids:
                logger.error(
                    "PID file exists and process is alive but not in registry: "
                    "path=%s pid=%s (worker_type=%s)",
                    pid_file,
                    pid,
                    self.worker_type,
                )

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
            "current_operation": None,
            "current_file": None,
            "progress_percent": None,
            "progress_updated_at": None,
        }

        # Only registry: get workers from WorkerManager
        registered_pids_set: set[int] = set()
        try:
            from ..core.worker_manager import get_worker_manager

            worker_manager = get_worker_manager()
            manager_status = worker_manager.get_worker_status()
            by_type = manager_status.get("by_type", {})

            if self.worker_type == "all":
                registered_pids = []
                for type_name, type_status in by_type.items():
                    registered_pids.extend(type_status.get("pids", []))
                registered_pids = list(dict.fromkeys(registered_pids))
            else:
                workers_by_type = by_type.get(self.worker_type, {})
                registered_pids = workers_by_type.get("pids", [])

            registered_pids_set = set(p for p in registered_pids if p)

            for pid in registered_pids:
                if pid:
                    proc_details = self._get_process_by_pid(pid)
                    if proc_details:
                        result["processes"].append(proc_details)
        except Exception as e:
            logger.warning(f"Failed to get workers from WorkerManager: {e}")

        # Verify: if PID file exists and process is alive but not in registry, log error
        self._verify_pid_files_against_registry(registered_pids_set)

        # Lock file info (for file watcher) — informational only, no fallback
        if self.worker_type in ("file_watcher", "all"):
            result["lock_file"] = self._get_lock_file_info()

        # Get recent log activity
        result["log_activity"] = self._get_recent_log_activity()

        # Read worker progress (current_operation, current_file, progress_percent) from status file
        status_data = self._get_worker_progress()
        if status_data:
            result["current_operation"] = status_data.get("current_operation")
            result["current_file"] = status_data.get("current_file")
            result["progress_percent"] = status_data.get("progress_percent")
            result["progress_updated_at"] = status_data.get("updated_at")

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
