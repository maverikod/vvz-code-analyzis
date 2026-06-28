"""
Advisory file lock to block other processes/threads from opening the same file.

Uses a .lock file next to the target path. On Unix uses fcntl.flock;
on Windows locking is not implemented (no-op) to avoid extra dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import math
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple
from unittest.mock import Mock

from .constants import DEFAULT_FILE_LOCK_TIMEOUT
from .runtime_lock_sessions import (
    acquire_file_advisory_lease,
    get_session_id_for_current_pid,
    normalize_lock_mode,
    release_file_advisory_lease,
)

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]


def _database_supports_lock_leases(database: Any) -> bool:
    """Return False for test doubles that cannot execute real lease DML."""
    return database is not None and not isinstance(database, Mock)


class FileLockTimeoutError(TimeoutError):
    """Raised when an advisory sidecar lock cannot be acquired before timeout."""


class FileLockHandle:
    """Held sidecar flock plus optional DB advisory lease."""

    def __init__(
        self,
        *,
        path: Path,
        lock_file: Any,
        lock_path: Path,
        mode: str,
        database: Any = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> None:
        """Initialize the instance."""
        self.path = path
        self.lock_file = lock_file
        self.lock_path = lock_path
        self.mode = normalize_lock_mode(mode)
        self.database = database
        self.session_id = session_id
        self.project_id = project_id
        self.file_path = file_path
        self.released = False

    def release(self, *, force_lease: bool = False) -> None:
        """Release the OS flock and best-effort DB lease."""
        if self.released:
            return
        self.released = True
        if (
            self.database is not None
            and self.session_id
            and self.project_id
            and self.file_path
            and self.mode != "none"
        ):
            try:
                release_file_advisory_lease(
                    self.database,
                    session_id=self.session_id,
                    project_id=self.project_id,
                    file_path=self.file_path,
                    lock_mode=self.mode,
                    force=force_lease,
                )
            except Exception as e:
                logger.warning("Lease release failed for %s: %s", self.path, e)
        if self.lock_file is not None and fcntl is not None:
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            except OSError as e:
                logger.warning("Unlock failed for %s: %s", self.lock_path, e)
        if self.lock_file is not None:
            self.lock_file.close()
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError as e:
            logger.debug("Remove lock file %s: %s", self.lock_path, e)

    def __enter__(self) -> "FileLockHandle":
        """Return enter."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Return exit."""
        self.release()


class PersistentFileLock:
    """Backward-compatible process-held advisory lock for a target file."""

    def __init__(self, path: Path, *, shared: bool = False) -> None:
        """Initialize the instance."""
        self.path = Path(path)
        self.shared = bool(shared)
        self._handle: Optional[FileLockHandle] = None

    @property
    def is_held(self) -> bool:
        """Return is held."""
        return self._handle is not None and not self._handle.released

    def acquire(self) -> "PersistentFileLock":
        """Return acquire."""
        if self.is_held:
            return self
        self._handle = acquire_file_lock(
            self.path,
            mode="block_write" if self.shared else "full",
        )
        return self

    def release(self) -> None:
        """Return release."""
        handle = self._handle
        self._handle = None
        if handle is not None:
            handle.release()

    def __enter__(self) -> "PersistentFileLock":
        """Return enter."""
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Return exit."""
        self.release()


_persistent_guard = threading.Lock()
_persistent_locks: Dict[Tuple[str, str, str], FileLockHandle] = {}


def _fcntl_flag_for_mode(mode: str) -> int:
    """Return fcntl flag for mode."""
    normalized = normalize_lock_mode(mode)
    if normalized == "shared":
        return fcntl.LOCK_SH if fcntl is not None else 0
    return fcntl.LOCK_EX if fcntl is not None else 0


def acquire_file_lock(
    path: Path,
    *,
    mode: str = "full",
    shared: Optional[bool] = None,
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    database: Any = None,
    project_id: Optional[str] = None,
    file_path: Optional[str] = None,
    session_id: Optional[str] = None,
    register_role: str = "command",
) -> FileLockHandle:
    """Acquire a sidecar flock and optional DB advisory lease."""
    target = Path(path)
    normalized_mode = "shared" if shared else normalize_lock_mode(mode)
    lock_path = Path(str(target) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w", encoding="utf-8")
    try:
        if fcntl is not None:
            flag = _fcntl_flag_for_mode(normalized_mode)
            # Resolve the effective wait budget. timeout=None means "use the
            # bounded default" (never block the worker thread forever); pass
            # math.inf explicitly to opt into a truly unbounded blocking flock.
            effective_timeout = (
                DEFAULT_FILE_LOCK_TIMEOUT if timeout is None else float(timeout)
            )
            if math.isinf(effective_timeout):
                fcntl.flock(lock_file.fileno(), flag)
            else:
                deadline = time.monotonic() + max(0.0, effective_timeout)
                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), flag | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as e:
                        if time.monotonic() >= deadline:
                            raise FileLockTimeoutError(
                                f"Timed out acquiring {normalized_mode} lock for {target}"
                            ) from e
                        time.sleep(max(0.001, float(poll_interval)))
        sid = session_id
        if (
            _database_supports_lock_leases(database)
            and project_id
            and file_path
            and normalized_mode != "none"
        ):
            sid = sid or get_session_id_for_current_pid(database, role=register_role)
            acquire_file_advisory_lease(
                database,
                session_id=sid,
                project_id=project_id,
                file_path=file_path,
                lock_mode=normalized_mode,
            )
        return FileLockHandle(
            path=target,
            lock_file=lock_file,
            lock_path=lock_path,
            mode=normalized_mode,
            database=database,
            session_id=sid,
            project_id=project_id,
            file_path=file_path,
        )
    except Exception:
        try:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        lock_file.close()
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass
        raise


def acquire_persistent_file_lock(
    path: Path,
    *,
    mode: str,
    database: Any,
    project_id: str,
    file_path: str,
    session_id: Optional[str] = None,
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    register_role: str = "command",
) -> FileLockHandle:
    """Acquire and retain a lock outside a context manager in this process."""
    sid = session_id or get_session_id_for_current_pid(database, role=register_role)
    key = (sid, str(project_id), str(file_path).replace("\\", "/"))
    with _persistent_guard:
        existing = _persistent_locks.get(key)
        if existing and not existing.released:
            acquire_file_advisory_lease(
                database,
                session_id=sid,
                project_id=project_id,
                file_path=file_path,
                lock_mode=mode,
            )
            return existing
        handle = acquire_file_lock(
            path,
            mode=mode,
            timeout=timeout,
            poll_interval=poll_interval,
            database=database,
            project_id=project_id,
            file_path=file_path,
            session_id=sid,
            register_role=register_role,
        )
        _persistent_locks[key] = handle
        return handle


def release_persistent_file_lock(
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    database: Any = None,
    lock_mode: Optional[str] = None,
    force: bool = True,
) -> bool:
    """Release a retained in-process lock and/or its DB lease."""
    key = (str(session_id), str(project_id), str(file_path).replace("\\", "/"))
    released = False
    with _persistent_guard:
        handle = _persistent_locks.pop(key, None)
    if handle is not None:
        handle.release(force_lease=force)
        released = True
    elif database is not None:
        release_file_advisory_lease(
            database,
            session_id=session_id,
            project_id=project_id,
            file_path=file_path,
            lock_mode=lock_mode,
            force=force,
        )
    return released


@contextmanager
def file_lock(
    path: Path,
    *,
    shared: bool = False,
    mode: str = "full",
    timeout: Optional[float] = None,
    poll_interval: float = 0.05,
    database: Any = None,
    project_id: Optional[str] = None,
    file_path: Optional[str] = None,
    session_id: Optional[str] = None,
    register_role: str = "command",
) -> Generator[None, None, None]:
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
    handle: Optional[FileLockHandle] = None
    try:
        handle = acquire_file_lock(
            Path(path),
            shared=shared,
            mode=mode,
            timeout=timeout,
            poll_interval=poll_interval,
            database=database,
            project_id=project_id,
            file_path=file_path,
            session_id=session_id,
            register_role=register_role,
        )
        yield
    finally:
        if handle is not None:
            handle.release()
