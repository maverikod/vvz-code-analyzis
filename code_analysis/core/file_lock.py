"""
Advisory file lock to block other processes/threads from opening the same file.

Uses a .lock file next to the target path. On Unix uses fcntl.flock;
on Windows locking is not implemented (no-op) to avoid extra dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]


@contextmanager
def file_lock(path: Path) -> Generator[None, None, None]:
    """
    Hold an exclusive advisory lock for the given file path.

    Creates path.lock (in the same directory) and locks it. Other processes
    using the same convention will block until the lock is released.
    path can be the actual file or its .tmp (lock is taken on path.lock).

    Args:
        path: File path to lock (e.g. /dir/file.py or /dir/file.py.tmp).

    Yields:
        None; lock is held for the duration of the context.
    """
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = None
    try:
        lock_file = open(lock_path, "w", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if lock_file is not None and fcntl is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError as e:
                logger.warning("Unlock failed for %s: %s", lock_path, e)
        if lock_file is not None:
            lock_file.close()
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError as e:
            logger.debug("Remove lock file %s: %s", lock_path, e)
