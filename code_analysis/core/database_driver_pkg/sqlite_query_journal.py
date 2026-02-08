"""
Query journal for SQLite driver: log each executed SQL for inspection and replay.

Writes JSON Lines (one JSON object per line). Each record has sql, params, and
optional success/error for recovery. Replay by reading lines and executing sql
with params (only success=True entries if replaying writes).
Supports rotation: when file size reaches max_bytes, current file is rotated to
 .1, .2, ... and a new file is opened.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default max size before rotation (100 MB)
DEFAULT_JOURNAL_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_JOURNAL_BACKUP_COUNT = 5


class SQLiteQueryJournal:
    """Append-only journal of SQL executions for logging and recovery, with rotation."""

    def __init__(
        self,
        log_path: str | Path,
        max_bytes: int = DEFAULT_JOURNAL_MAX_BYTES,
        backup_count: int = DEFAULT_JOURNAL_BACKUP_COUNT,
    ) -> None:
        """Open journal file for appending.

        Args:
            log_path: Path to journal file (e.g. .jsonl). Parent dir is created if needed.
            max_bytes: Rotate when file size reaches this (default 100 MB). 0 disables rotation.
            backup_count: Number of rotated files to keep (.1, .2, ...).
        """
        self._path = Path(log_path).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._file = open(
            self._path,
            "a",
            encoding="utf-8",
            newline="\n",
        )
        self._lock = threading.Lock()

    def _rotate_if_needed(self) -> None:
        """If current file size >= max_bytes, rotate and open new file. Call with _lock held."""
        if self._file is None or self._max_bytes <= 0:
            return
        try:
            self._file.flush()
            if self._path.exists() and self._path.stat().st_size >= self._max_bytes:
                self._file.close()
                self._file = None
                # Shift backups: .1 -> .2, .2 -> .3, ... then current -> .1
                for i in range(self._backup_count - 1, 0, -1):
                    old = Path(str(self._path) + f".{i}")
                    new = Path(str(self._path) + f".{i + 1}")
                    if old.exists():
                        if new.exists():
                            new.unlink()
                        old.rename(new)
                self._path.rename(Path(str(self._path) + ".1"))
                self._file = open(
                    self._path,
                    "a",
                    encoding="utf-8",
                    newline="\n",
                )
        except Exception as e:
            logger.warning("Query journal rotation failed: %s", e)
            if self._file is None:
                self._file = open(
                    self._path,
                    "a",
                    encoding="utf-8",
                    newline="\n",
                )

    def write(
        self,
        sql: str,
        params: Optional[tuple | list | dict] = None,
        transaction_id: Optional[str] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Append one journal entry (one line of JSON).

        Args:
            sql: SQL statement.
            params: Bound parameters (tuple, list, or dict); stored for replay.
            transaction_id: Optional transaction ID for context.
            success: Whether execution succeeded.
            error: Error message if success is False.
        """
        with self._lock:
            if self._file is None:
                return
            try:
                self._rotate_if_needed()
                # Serialize params for JSON (tuple/list/dict only)
                params_ser: Optional[List[Any]] | Optional[Dict[str, Any]]
                if params is None:
                    params_ser = None
                elif isinstance(params, dict):
                    params_ser = params
                else:
                    params_ser = list(params)
                entry: Dict[str, Any] = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "sql": sql,
                    "params": params_ser,
                    "success": success,
                }
                if transaction_id is not None:
                    entry["transaction_id"] = transaction_id
                if error is not None:
                    entry["error"] = error
                line = json.dumps(entry, ensure_ascii=False) + "\n"
                self._file.write(line)
                self._file.flush()
            except Exception as e:
                logger.warning("Query journal write failed: %s", e)

    def close(self) -> None:
        """Close the journal file."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None

    @property
    def path(self) -> Path:
        """Return journal file path."""
        return self._path


def replay_journal(
    journal_path: str | Path,
    execute_fn: Any,
    *,
    only_success: bool = True,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Replay journal entries by calling execute_fn(sql, params) for each.

    Args:
        journal_path: Path to .jsonl journal file.
        execute_fn: Callable(sql: str, params: Optional[tuple|dict]) -> None.
            Typically a database execute; params are passed as returned from JSON
            (list -> tuple for positional, dict for named).
        only_success: If True, replay only entries with success=True.
        limit: Max number of entries to replay (None = all).

    Returns:
        Dict with keys: replayed (int), failed (int), errors (list of str).
    """
    path = Path(journal_path)
    if not path.exists():
        return {"replayed": 0, "failed": 0, "errors": ["Journal file not found"]}
    replayed = 0
    failed = 0
    errors: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if limit is not None and replayed + failed >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON: {e}")
                failed += 1
                continue
            if only_success and not entry.get("success", True):
                continue
            sql = entry.get("sql")
            if not sql:
                errors.append("Missing sql in entry")
                failed += 1
                continue
            params_raw = entry.get("params")
            if params_raw is None:
                params = None
            elif isinstance(params_raw, dict):
                params = params_raw
            elif isinstance(params_raw, list):
                params = tuple(params_raw)
            else:
                params = None
            try:
                execute_fn(sql, params)
                replayed += 1
            except Exception as e:
                failed += 1
                errors.append(f"{sql[:50]}...: {e}")
    return {"replayed": replayed, "failed": failed, "errors": errors}
