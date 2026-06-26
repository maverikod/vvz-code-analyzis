"""
Raw finding buffer for paginated search session result production.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
from pathlib import Path

LOCK_FILENAME = "assembler.lock"


class RawFindingBuffer:
    """
    Accumulation subdirectory where the main search thread writes one finding
    per file until a result block is assembled.
    """

    def __init__(self, buffer_dir: Path) -> None:
        """Initialize the instance."""
        self._buffer_dir = buffer_dir.resolve()
        self._buffer_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._buffer_dir / LOCK_FILENAME

    @property
    def buffer_dir(self) -> Path:
        """Absolute path to the buffer directory."""
        return self._buffer_dir

    @property
    def lock_path(self) -> Path:
        """Absolute path to the assembler lock file."""
        return self._lock_path

    def append_finding(self, finding_id: str, payload: dict) -> Path:
        """
        Atomically publish one finding JSON file and return its path.

        Writers (search producers) write to a ``.json.tmp`` sidecar, fsync it,
        then ``os.replace`` it to the final ``.json`` name. The assembler only
        ever sees fully written ``.json`` files via ``list_findings`` and never
        observes a partial write — ``os.replace`` is atomic within one filesystem.
        """
        final_path = self._buffer_dir / f"{finding_id}.json"
        tmp_path = self._buffer_dir / f"{finding_id}.json.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, final_path)
        return final_path

    def list_findings(self) -> list[Path]:
        """Return finding file paths sorted by modification time."""
        paths = [
            path
            for path in self._buffer_dir.iterdir()
            if path.is_file() and path.suffix == ".json"
        ]
        return sorted(paths, key=lambda item: item.stat().st_mtime)

    def total_bytes(self) -> int:
        """Return total byte size of all finding files."""
        return sum(path.stat().st_size for path in self.list_findings())

    def remove_findings(self, paths: list[Path]) -> None:
        """Delete assembled finding files from the buffer."""
        for path in paths:
            if path.exists():
                path.unlink()

    def try_acquire_lock(self) -> bool:
        """
        Acquire the buffer lock or reclaim a stale lock.

        Returns:
            True when this process owns the lock; False when a live owner holds it.
        """
        if self._lock_path.is_file():
            owner_pid = self._read_lock_pid()
            if owner_pid is not None and self._pid_is_alive(owner_pid):
                return False
            self._lock_path.unlink(missing_ok=True)

        self._write_lock_pid(os.getpid())
        return True

    def release_lock(self) -> None:
        """Release the buffer lock when owned by this process."""
        if not self._lock_path.is_file():
            return
        owner_pid = self._read_lock_pid()
        if owner_pid == os.getpid():
            self._lock_path.unlink(missing_ok=True)

    def delete_buffer(self) -> None:
        """Remove all finding files, the lock, and the buffer directory."""
        for path in self.list_findings():
            path.unlink(missing_ok=True)
        self._lock_path.unlink(missing_ok=True)
        if self._buffer_dir.is_dir():
            self._buffer_dir.rmdir()

    def _read_lock_pid(self) -> int | None:
        """Return read lock pid."""
        try:
            raw = self._lock_path.read_text(encoding="utf-8").strip()
            return int(raw)
        except (OSError, ValueError):
            return None

    def _write_lock_pid(self, pid: int) -> None:
        """Return write lock pid."""
        self._buffer_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._lock_path.with_suffix(self._lock_path.suffix + ".tmp")
        tmp_path.write_text(str(pid), encoding="utf-8")
        os.replace(tmp_path, self._lock_path)

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        """Return pid is alive."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        else:
            return True
