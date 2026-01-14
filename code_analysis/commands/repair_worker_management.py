"""
Commands for managing repair worker process.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import multiprocessing
import time
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class RepairWorkerManager:
    """
    Manager for repair worker process.

    Handles:
    - Starting worker in separate process
    - Stopping worker gracefully
    - Getting worker status
    """

    def __init__(
        self,
        db_path: Path,
        project_id: str,
        root_dir: Path,
        version_dir: str,
        worker_log_path: Optional[Path] = None,
        batch_size: int = 10,
        poll_interval: int = 30,
    ):
        """
        Initialize repair worker manager.

        Args:
            db_path: Path to database file
            project_id: Project ID
            root_dir: Project root directory
            version_dir: Version directory for deleted files
            worker_log_path: Path to worker log file (optional)
            batch_size: Number of files to process per batch (default: 10)
            poll_interval: Interval in seconds between repair cycles (default: 30)
        """
        self.db_path = db_path
        self.project_id = project_id
        self.root_dir = root_dir
        self.version_dir = version_dir
        self.worker_log_path = worker_log_path
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self._process: Optional[multiprocessing.Process] = None

    def start(self) -> Dict[str, Any]:
        """
        Start repair worker in separate process.

        Returns:
            Dictionary with start result
        """
        # Check if worker is already running
        existing_processes = self._find_worker_processes()
        if existing_processes:
            return {
                "success": False,
                "message": f"Repair worker already running (PID: {existing_processes[0]['pid']})",
                "pid": existing_processes[0]["pid"],
            }

        try:
            from ..core.repair_worker_pkg.runner import run_repair_worker

            # Start worker process
            process = multiprocessing.Process(
                target=run_repair_worker,
                args=(
                    str(self.db_path),
                    self.project_id,
                    str(self.root_dir),
                    self.version_dir,
                ),
                kwargs={
                    "batch_size": self.batch_size,
                    "poll_interval": self.poll_interval,
                    "worker_log_path": (
                        str(self.worker_log_path) if self.worker_log_path else None
                    ),
                },
                daemon=True,
            )
            process.start()
            self._process = process

            # Wait a bit to check if process started successfully
            time.sleep(0.5)
            if process.is_alive():
                logger.info(f"Repair worker started successfully (PID: {process.pid})")

                # Register worker in WorkerManager
                try:
                    from ..core.worker_manager import get_worker_manager

                    worker_manager = get_worker_manager()
                    worker_manager.register_worker(
                        "repair",
                        {
                            "pid": process.pid,
                            "process": process,
                            "name": f"repair_{self.project_id}",
                        },
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to register repair worker in WorkerManager: {e}"
                    )

                return {
                    "success": True,
                    "message": f"Repair worker started (PID: {process.pid})",
                    "pid": process.pid,
                }
            else:
                return {
                    "success": False,
                    "message": "Repair worker process failed to start",
                    "exit_code": process.exitcode,
                }

        except Exception as e:
            logger.error(f"Error starting repair worker: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error starting repair worker: {e}",
                "error": str(e),
            }

    def stop(self, timeout: int = 10, force: bool = False) -> Dict[str, Any]:
        """
        Stop repair worker gracefully.

        Args:
            timeout: Timeout in seconds before force kill (default: 10)
            force: If True, immediately kill with SIGKILL (default: False)

        Returns:
            Dictionary with stop result
        """
        processes = self._find_worker_processes()
        if not processes:
            return {
                "success": True,
                "message": "No repair worker processes found",
                "killed": [],
            }

        killed = []
        failed = []

        for proc_info in processes:
            pid = proc_info["pid"]
            try:
                import psutil

                proc = psutil.Process(pid)
                if force:
                    # Immediately kill with SIGKILL
                    proc.kill()
                    logger.warning(f"Force killed repair worker process (PID: {pid})")
                    time.sleep(0.1)
                else:
                    # Try graceful shutdown first
                    proc.terminate()
                    logger.info(f"Sent SIGTERM to repair worker process (PID: {pid})")
                    # Wait for process to terminate
                    try:
                        proc.wait(timeout=timeout)
                        logger.info(f"Repair worker process terminated (PID: {pid})")
                    except psutil.TimeoutExpired:
                        # Force kill if still running
                        proc.kill()
                        logger.warning(
                            f"Force killed repair worker process (PID: {pid}) after timeout"
                        )
                        time.sleep(0.2)

                if not proc.is_running():
                    killed.append({"pid": pid})
                else:
                    failed.append({"pid": pid, "error": "Still running"})

            except Exception as e:
                logger.error(f"Failed to stop repair worker process (PID: {pid}): {e}")
                failed.append({"pid": pid, "error": str(e)})

        if self._process:
            self._process = None

        return {
            "success": len(failed) == 0,
            "message": f"Stopped {len(killed)} process(es), {len(failed)} failed",
            "killed": killed,
            "failed": failed,
        }

    def status(self) -> Dict[str, Any]:
        """
        Get repair worker status.

        Returns:
            Dictionary with worker status information
        """
        processes = self._find_worker_processes()
        result = {
            "worker_type": "repair",
            "is_running": len(processes) > 0,
            "processes": [],
            "log_activity": None,
        }

        # Get process details
        for proc_info in processes:
            pid = proc_info.get("pid")
            if pid:
                proc_details = self._get_process_by_pid(pid)
                if proc_details:
                    result["processes"].append(proc_details)

        # Get log activity
        if self.worker_log_path and self.worker_log_path.exists():
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

    def _find_worker_processes(self) -> list[Dict[str, Any]]:
        """Find repair worker processes by name pattern."""
        processes = []
        try:
            import psutil

            for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
                try:
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if (
                        "repair_worker" in cmdline.lower()
                        or "run_repair_worker" in cmdline
                    ):
                        processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            logger.warning("psutil not available, cannot find processes")
        except Exception as e:
            logger.warning(f"Error finding processes: {e}")
        return processes

    def _get_process_by_pid(self, pid: int) -> Optional[Dict[str, Any]]:
        """Get process details by PID."""
        try:
            import psutil
            from datetime import datetime

            proc = psutil.Process(pid)
            create_time = datetime.fromtimestamp(proc.create_time())
            uptime = (datetime.now() - create_time).total_seconds()

            return {
                "pid": pid,
                "cpu_percent": proc.cpu_percent(interval=0.1),
                "memory_mb": proc.memory_info().rss / 1024 / 1024,
                "create_time": create_time.isoformat(),
                "uptime_seconds": int(uptime),
                "status": proc.status(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        except Exception as e:
            logger.warning(f"Error getting process info: {e}")
            return None

    def _get_recent_log_activity(self, lines: int = 10) -> Dict[str, Any]:
        """Get recent log activity."""
        if not self.worker_log_path or not self.worker_log_path.exists():
            return {"available": False}

        try:
            from datetime import datetime

            with open(self.worker_log_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                recent_lines = (
                    all_lines[-lines:] if len(all_lines) > lines else all_lines
                )

            last_entry = None
            if recent_lines:
                last_line = recent_lines[-1].strip()
                # Try to extract timestamp
                for line in reversed(recent_lines):
                    parts = line.split(" | ", 2)
                    if len(parts) == 3:
                        try:
                            timestamp_match = datetime.strptime(
                                parts[0].strip(), "%Y-%m-%d %H:%M:%S"
                            )
                            last_entry = {
                                "timestamp": timestamp_match.isoformat(),
                                "age_seconds": int(
                                    (datetime.now() - timestamp_match).total_seconds()
                                ),
                                "line": last_line[:200],
                            }
                            break
                        except ValueError:
                            pass

            return {
                "available": True,
                "file_size_mb": self.worker_log_path.stat().st_size / 1024 / 1024,
                "last_entry": last_entry,
                "recent_lines_count": len(recent_lines),
            }
        except Exception as e:
            logger.warning(f"Error reading log file: {e}")
            return {"available": True, "error": str(e)}
