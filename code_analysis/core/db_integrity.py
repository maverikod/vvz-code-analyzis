"""
SQLite database integrity helpers.

This module provides small, dependency-free utilities to:
- verify physical integrity of a SQLite database file;
- backup a corrupted database (+ sidecar files);
- recreate a fresh database file when corruption is detected.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class SQLiteRepairResult:
    """
    Result of SQLite integrity verification / repair.

    Attributes:
        ok: Whether DB integrity is OK.
        repaired: Whether a repair action was performed (backup + recreate).
        message: Human-readable summary.
        backup_paths: Paths of created backups (db + sidecars), if any.
    """

    ok: bool
    repaired: bool
    message: str
    backup_paths: Tuple[str, ...] = ()


def _sidecar_paths(db_path: Path) -> List[Path]:
    """
    Return common SQLite sidecar paths for a database.

    Args:
        db_path: Path to main SQLite file.

    Returns:
        List of possible sidecar files (may or may not exist).
    """
    return [
        db_path.with_suffix(db_path.suffix + "-wal"),
        db_path.with_suffix(db_path.suffix + "-shm"),
        db_path.with_suffix(db_path.suffix + "-journal"),
    ]


def check_sqlite_integrity(
    db_path: Path, *, timeout_seconds: float = 2.0
) -> SQLiteRepairResult:
    """
    Run a fast integrity check against SQLite file.

    Notes:
        - Uses `PRAGMA quick_check(1)` first, then falls back to `integrity_check`
          if needed.
        - Any sqlite3.DatabaseError is treated as corruption.

    Args:
        db_path: Path to SQLite file.
        timeout_seconds: Connection timeout.

    Returns:
        SQLiteRepairResult describing whether DB is OK.
    """
    if not db_path.exists():
        return SQLiteRepairResult(
            ok=True, repaired=False, message="Database file does not exist"
        )

    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout_seconds)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA quick_check(1)")
            row = cur.fetchone()
            msg = (row[0] if row else "") or ""
            if str(msg).lower() == "ok":
                return SQLiteRepairResult(
                    ok=True, repaired=False, message="quick_check: ok"
                )

            # Fallback to full integrity_check for a more explicit message.
            cur.execute("PRAGMA integrity_check")
            rows = cur.fetchall() or []
            messages = [str(r[0]) for r in rows if r and r[0]]
            if len(messages) == 1 and messages[0].lower() == "ok":
                return SQLiteRepairResult(
                    ok=True, repaired=False, message="integrity_check: ok"
                )
            return SQLiteRepairResult(
                ok=False,
                repaired=False,
                message="integrity_check failed: " + "; ".join(messages[:5]),
            )
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        return SQLiteRepairResult(
            ok=False, repaired=False, message=f"sqlite3.DatabaseError: {e}"
        )
    except Exception as e:
        return SQLiteRepairResult(
            ok=False, repaired=False, message=f"Integrity check error: {e}"
        )


def backup_sqlite_files(
    db_path: Path,
    *,
    backup_dir: Optional[Path] = None,
    include_sidecars: bool = True,
) -> Tuple[str, ...]:
    """
    Create filesystem backups of a SQLite db file (+ sidecars).

    Args:
        db_path: Path to SQLite db file.
        backup_dir: Directory where to place backups (defaults to db_path.parent).
        include_sidecars: If True, also backup -wal/-shm/-journal if present.

    Returns:
        Tuple of created backup file paths (as strings).
    """
    backup_root = (backup_dir or db_path.parent).resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")

    sources: List[Path] = [db_path]
    if include_sidecars:
        sources.extend(_sidecar_paths(db_path))

    created: List[str] = []
    for src in sources:
        if not src.exists():
            continue
        dst = backup_root / f"{src.name}.corrupt-backup.{ts}"
        shutil.copy2(src, dst)
        created.append(str(dst))
    return tuple(created)


def recreate_sqlite_database_file(db_path: Path) -> None:
    """
    Delete SQLite file and its sidecars (if any) to allow recreating from scratch.

    Args:
        db_path: Path to SQLite file.
    """
    paths: List[Path] = [db_path]
    paths.extend(_sidecar_paths(db_path))
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            # Best-effort cleanup; remaining sidecars are not fatal.
            pass


def ensure_sqlite_integrity_or_recreate(
    db_path: Path,
    *,
    backup_dir: Optional[Path] = None,
) -> SQLiteRepairResult:
    """
    Ensure SQLite file integrity; if corrupted, backup and recreate.

    Args:
        db_path: Path to SQLite file.
        backup_dir: Where to store backups.

    Returns:
        SQLiteRepairResult with repaired=True if DB was recreated.
    """
    check = check_sqlite_integrity(db_path)
    if check.ok:
        return check

    backups = backup_sqlite_files(db_path, backup_dir=backup_dir, include_sidecars=True)
    recreate_sqlite_database_file(db_path)
    return SQLiteRepairResult(
        ok=True,
        repaired=True,
        message=f"Database was corrupted ({check.message}); backed up {len(backups)} file(s) and recreated",
        backup_paths=backups,
    )
