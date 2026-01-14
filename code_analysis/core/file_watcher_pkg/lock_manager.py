"""
Lock file manager for file watcher worker.

Manages lock files in service state directory (locks_dir) to prevent multiple instances.
Lock files are stored in {locks_dir}/{project_id}/{lock_key}.lock format.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import hashlib
import json
import logging
import os
import socket
import time
from pathlib import Path

from ..project_resolution import normalize_root_dir

logger = logging.getLogger(__name__)


class LockManager:
    """
    Manages lock files for file watcher worker.

    Lock files are created in service state directory (locks_dir), not in watched directories.
    This implements Step 4 of the refactor plan: directory locking to prevent parallel scans.

    Lock file path: {locks_dir}/{project_id}/{lock_key}.lock
    where lock_key is a stable hash of the resolved absolute watch_dir path.
    """

    def __init__(
        self,
        locks_dir: Path,
        project_id: str,
    ):
        """
        Initialize lock manager.

        Args:
            locks_dir: Service state directory for lock files (from StoragePaths).
            project_id: Project identifier (UUID4 string).
        """
        self.locks_dir = Path(locks_dir).resolve()
        self.project_id = project_id
        # Ensure locks directory exists
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        # Project-specific lock directory
        self.project_locks_dir = self.locks_dir / project_id
        self.project_locks_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock_key(self, watch_dir: Path) -> str:
        """
        Generate stable lock key from watch directory path.

        Uses SHA256 hash of normalized absolute path to create a stable identifier.

        Args:
            watch_dir: Watch directory path (will be normalized to absolute).

        Returns:
            Lock key string (hex digest).
        """
        normalized = str(normalize_root_dir(watch_dir))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _get_lock_path(self, watch_dir: Path) -> Path:
        """
        Get lock file path for a watch directory.

        Args:
            watch_dir: Watch directory path.

        Returns:
            Absolute Path to lock file.
        """
        lock_key = self._get_lock_key(watch_dir)
        return self.project_locks_dir / f"{lock_key}.lock"

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
            root_dir: Root watched directory (will be normalized to absolute).
            pid: Process ID of current worker

        Returns:
            True if lock acquired, False otherwise
        """
        normalized_root = normalize_root_dir(root_dir)
        lock_path = self._get_lock_path(normalized_root)

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
                            f"for {normalized_root}. Another worker is running."
                        )
                        return False

                    # Process is dead, remove stale lock
                    logger.info(
                        f"Removing stale lock file (process {existing_pid} is dead) "
                        f"for {normalized_root}"
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
                "timestamp": time.time(),
                "watch_dir": str(normalized_root),
                "worker_name": "file_watcher_worker",
                "hostname": socket.gethostname(),
                "project_id": self.project_id,
            }

            # Atomic write: write to temp file, then rename
            temp_path = lock_path.with_suffix(f"{lock_path.suffix}.tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)
            temp_path.replace(lock_path)

            logger.info(
                f"Acquired lock for {normalized_root} (PID: {pid}, "
                f"lock_path: {lock_path})"
            )
            return True
        except OSError as e:
            logger.error(f"Failed to create lock file {lock_path}: {e}")
            return False

    def release_lock(self, root_dir: Path) -> None:
        """
        Release lock for root directory.

        Args:
            root_dir: Root watched directory (will be normalized to absolute).
        """
        normalized_root = normalize_root_dir(root_dir)
        lock_path = self._get_lock_path(normalized_root)
        try:
            if lock_path.exists():
                lock_path.unlink()
                logger.info(
                    f"Released lock for {normalized_root} (lock_path: {lock_path})"
                )
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
            root_dir: Root watched directory (will be normalized to absolute).

        Returns:
            True if lock file exists, False otherwise
        """
        normalized_root = normalize_root_dir(root_dir)
        lock_path = self._get_lock_path(normalized_root)
        return lock_path.exists()
