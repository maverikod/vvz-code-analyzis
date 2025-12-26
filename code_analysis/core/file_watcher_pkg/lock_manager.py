"""
Lock file manager for file watcher worker.

Manages .lock files in root watched directories to prevent multiple instances.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import os
import socket
from pathlib import Path

logger = logging.getLogger(__name__)


class LockManager:
    """
    Manages lock files for file watcher worker.

    Lock files are created only in root watched directories from config,
    not in subdirectories.
    """

    def __init__(self, lock_file_name: str = ".file_watcher.lock"):
        """
        Initialize lock manager.

        Args:
            lock_file_name: Name of lock file (default: ".file_watcher.lock")
        """
        self.lock_file_name = lock_file_name

    def acquire_lock(self, root_dir: Path, pid: int) -> bool:
        """
        Acquire lock for root directory.

        Process:
        1. Check if lock file exists
        2. If exists, check if process is alive (by PID)
        3. If process dead, remove stale lock
        4. Create new lock file atomically
        5. Write lock info

        Args:
            root_dir: Root watched directory
            pid: Process ID of current worker

        Returns:
            True if lock acquired, False otherwise
        """
        lock_path = root_dir / self.lock_file_name

        # Check if lock exists
        if lock_path.exists():
            try:
                # Read existing lock
                with open(lock_path, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)
                    existing_pid = lock_data.get("pid")

                    # Check if process is alive
                    if existing_pid and self._is_process_alive(existing_pid):
                        logger.warning(
                            f"Lock file exists and process {existing_pid} is alive "
                            f"in {root_dir}. Another worker is running."
                        )
                        return False

                    # Process is dead, remove stale lock
                    logger.info(
                        f"Removing stale lock file (process {existing_pid} is dead)"
                    )
                    lock_path.unlink()
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Error reading lock file {lock_path}: {e}")
                # Try to remove corrupted lock file
                try:
                    lock_path.unlink()
                except OSError:
                    pass

        # Create new lock file
        try:
            lock_data = {
                "pid": pid,
                "timestamp": (
                    os.path.getmtime(lock_path.parent)
                    if lock_path.parent.exists()
                    else 0
                ),
                "worker_name": "file_watcher_worker",
                "hostname": socket.gethostname(),
            }

            # Atomic write: write to temp file, then rename
            temp_path = lock_path.with_suffix(f"{lock_path.suffix}.tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)
            temp_path.replace(lock_path)

            logger.info(f"Acquired lock for {root_dir} (PID: {pid})")
            return True
        except OSError as e:
            logger.error(f"Failed to create lock file {lock_path}: {e}")
            return False

    def release_lock(self, root_dir: Path) -> None:
        """
        Release lock for root directory.

        Args:
            root_dir: Root watched directory
        """
        lock_path = root_dir / self.lock_file_name
        try:
            if lock_path.exists():
                lock_path.unlink()
                logger.info(f"Released lock for {root_dir}")
        except OSError as e:
            logger.warning(f"Failed to remove lock file {lock_path}: {e}")

    def _is_process_alive(self, pid: int) -> bool:
        """
        Check if process with given PID is alive.

        Args:
            pid: Process ID

        Returns:
            True if process is alive, False otherwise
        """
        try:
            # Try to send signal 0 (doesn't kill process, just checks if it exists)
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def has_lock(self, root_dir: Path) -> bool:
        """
        Check if lock file exists for root directory.

        Args:
            root_dir: Root watched directory

        Returns:
            True if lock file exists, False otherwise
        """
        lock_path = root_dir / self.lock_file_name
        return lock_path.exists()
