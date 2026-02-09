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

import re
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# Tables that were renamed during migration; FKs in other tables point to these until fixed.
_STALE_FK_TARGETS = ("temp_files", "temp_methods")


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
        - Most sqlite3.DatabaseError cases are treated as corruption.
        - IMPORTANT: transient lock/busy errors (e.g. during indexing) are NOT
          treated as corruption. They should not trigger safe-mode markers.

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
        msg = str(e).lower()
        # Transient errors under concurrent access (not corruption).
        if "database is locked" in msg or "database is busy" in msg or "locked" in msg:
            return SQLiteRepairResult(
                ok=True,
                repaired=False,
                message=f"sqlite3.DatabaseError (transient, ignored): {e}",
            )
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
    """Delete SQLite file and its sidecars (if any) to allow recreating from scratch.

    Args:
        db_path: Path to SQLite file.

    Returns:
        None
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
    """Ensure SQLite file integrity; if corrupted, backup and recreate.

    Notes:
        If a corruption marker exists for this DB, it is best-effort cleared after
        successful recreation.

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

    # If we repaired the DB file, we can clear the persistent marker.
    try:
        clear_corruption_marker(db_path)
    except Exception:
        pass

    return SQLiteRepairResult(
        ok=True,
        repaired=True,
        message=(
            f"Database was corrupted ({check.message}); backed up {len(backups)} file(s) and recreated"
        ),
        backup_paths=backups,
    )


def recover_files_table_if_needed(
    db_path: Path, *, timeout_seconds: float = 2.0
) -> bool:
    """If table 'files' is missing but 'temp_files' exists, rename temp_files to files.

    Used after an aborted schema migration (e.g. in db_driver) that left only temp_files.
    Call this from repair_sqlite_database (or similar) so recovery is explicit, not on connect.

    Args:
        db_path: Path to SQLite db file.
        timeout_seconds: Connection timeout.

    Returns:
        True if the rename was performed; False if schema was already OK or recovery not applicable.
    """
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout_seconds)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
            )
            if cur.fetchone() is not None:
                return False
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='temp_files'"
            )
            if cur.fetchone() is None:
                return False
            cur.execute("ALTER TABLE temp_files RENAME TO files")
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


# Canonical CREATE TABLE for entity_cross_ref with correct FKs (files, methods).
# Used when table has stale FKs to temp_files/temp_methods after a partial migration.
_ENTITY_CROSS_REF_CREATE = """
CREATE TABLE entity_cross_ref (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caller_class_id INTEGER NULL,
    caller_method_id INTEGER NULL,
    caller_function_id INTEGER NULL,
    callee_class_id INTEGER NULL,
    callee_method_id INTEGER NULL,
    callee_function_id INTEGER NULL,
    ref_type TEXT NOT NULL,
    file_id INTEGER NULL,
    line INTEGER NULL,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (caller_class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (caller_method_id) REFERENCES methods(id) ON DELETE CASCADE,
    FOREIGN KEY (caller_function_id) REFERENCES functions(id) ON DELETE CASCADE,
    FOREIGN KEY (callee_class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (callee_method_id) REFERENCES methods(id) ON DELETE CASCADE,
    FOREIGN KEY (callee_function_id) REFERENCES functions(id) ON DELETE CASCADE,
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
    CHECK (
        (caller_class_id IS NOT NULL AND caller_method_id IS NULL AND caller_function_id IS NULL)
        OR (caller_class_id IS NULL AND caller_method_id IS NOT NULL AND caller_function_id IS NULL)
        OR (caller_class_id IS NULL AND caller_method_id IS NULL AND caller_function_id IS NOT NULL)
    ),
    CHECK (
        (callee_class_id IS NOT NULL AND callee_method_id IS NULL AND callee_function_id IS NULL)
        OR (callee_class_id IS NULL AND callee_method_id IS NOT NULL AND callee_function_id IS NULL)
        OR (callee_class_id IS NULL AND callee_method_id IS NULL AND callee_function_id IS NOT NULL)
    )
)
"""
_ENTITY_CROSS_REF_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_class ON entity_cross_ref(caller_class_id) WHERE caller_class_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_method ON entity_cross_ref(caller_method_id) WHERE caller_method_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_caller_function ON entity_cross_ref(caller_function_id) WHERE caller_function_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_class ON entity_cross_ref(callee_class_id) WHERE callee_class_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_method ON entity_cross_ref(callee_method_id) WHERE callee_method_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_callee_function ON entity_cross_ref(callee_function_id) WHERE callee_function_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_entity_cross_ref_file ON entity_cross_ref(file_id)",
]


def _tables_with_stale_fks(cur: sqlite3.Cursor) -> List[str]:
    """Return list of table names that have FK pointing to temp_files or temp_methods."""
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    all_tables = [r[0] for r in cur.fetchall()]
    stale: List[str] = []
    for table in all_tables:
        if table in _STALE_FK_TARGETS:
            continue
        cur.execute(f"PRAGMA foreign_key_list({table})")
        refs = {row[2] for row in cur.fetchall()}
        if refs & set(_STALE_FK_TARGETS):
            stale.append(table)
    return stale


def fix_all_stale_fks_in_connection(conn: sqlite3.Connection) -> bool:
    """Recreate any table that has FK to temp_files or temp_methods (fixes stale refs).

    When schema_sync renames files->temp_files (or methods->temp_methods), SQLite
    updates all FKs in the database to point at temp_*. After DROP temp_*, every
    table that referenced files/methods is left with broken FKs. This recreates
    each such table with REFERENCES files(id) / methods(id) and preserves data.

    Args:
        conn: Open SQLite connection (same one used for migration).

    Returns:
        True if at least one table was recreated; False if no fix needed.
    """
    cur = conn.cursor()
    stale_tables = _tables_with_stale_fks(cur)
    if not stale_tables:
        return False
    fixed = False
    for table in stale_tables:
        cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            continue
        create_sql = row[0]
        create_sql = create_sql.replace('REFERENCES "temp_files"', 'REFERENCES "files"')
        create_sql = create_sql.replace("REFERENCES temp_files", "REFERENCES files")
        create_sql = create_sql.replace('REFERENCES "temp_methods"', 'REFERENCES "methods"')
        create_sql = create_sql.replace("REFERENCES temp_methods", "REFERENCES methods")
        # New table name to avoid conflict
        create_new = re.sub(
            r"(CREATE TABLE\s+(?:\w+\.)?)" + re.escape(table) + r"(\s*\()",
            r"\1" + table + "_new" + r"\2",
            create_sql,
            count=1,
        )
        cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name = ? AND name NOT LIKE 'sqlite_%'",
            (table,),
        )
        index_sqls = [r[0] for r in cur.fetchall() if r and r[0]]
        cur.execute(create_new)
        cur.execute(f"INSERT INTO {table}_new SELECT * FROM {table}")
        cur.execute(f"DROP TABLE {table}")
        cur.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
        for idx_sql in index_sqls:
            if idx_sql:
                try:
                    cur.execute(idx_sql)
                except sqlite3.OperationalError:
                    pass
        fixed = True
    return fixed


def fix_entity_cross_ref_stale_fks_in_connection(conn: sqlite3.Connection) -> bool:
    """Recreate entity_cross_ref if any of its FK target tables are missing (stale refs).

    When schema_sync renames files->temp_files then drops temp_files, entity_cross_ref
    keeps REFERENCES temp_files(id) and breaks. This recreates the table with correct
    REFERENCES files(id), methods(id). Also fixes when any referenced table is missing.

    Args:
        conn: Open SQLite connection (same one used for migration).

    Returns:
        True if the table was recreated; False if no fix needed.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_cross_ref'"
    )
    if cur.fetchone() is None:
        return False
    cur.execute("PRAGMA foreign_key_list(entity_cross_ref)")
    rows = cur.fetchall()
    ref_tables = {row[2] for row in rows}
    if not ref_tables:
        return False
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN (%s)"
        % ",".join("?" * len(ref_tables)),
        tuple(ref_tables),
    )
    existing = {r[0] for r in cur.fetchall()}
    if ref_tables <= existing:
        return False
    cur.execute("DROP TABLE entity_cross_ref")
    cur.execute(_ENTITY_CROSS_REF_CREATE)
    for idx_sql in _ENTITY_CROSS_REF_INDEXES:
        cur.execute(idx_sql)
    return True


def fix_all_stale_fks(
    db_path: Path, *, timeout_seconds: float = 2.0
) -> bool:
    """Recreate all tables that have FK to temp_files or temp_methods (stale after migration).

    Opens the DB and calls fix_all_stale_fks_in_connection. Use for one-off repair
    of an already-broken database (e.g. after a migration that ran without the fix).

    Args:
        db_path: Path to SQLite db file.
        timeout_seconds: Connection timeout.

    Returns:
        True if at least one table was recreated; False if no fix needed.
    """
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout_seconds)
        try:
            fixed = fix_all_stale_fks_in_connection(conn)
            if fixed:
                conn.commit()
            return fixed
        finally:
            conn.close()
    except Exception:
        return False


def fix_entity_cross_ref_stale_fks(
    db_path: Path, *, timeout_seconds: float = 2.0
) -> bool:
    """Recreate entity_cross_ref if it has FK to temp_files or temp_methods (stale after migration).

    When schema_sync renames files->temp_files and methods->temp_methods, SQLite updates
    FKs in entity_cross_ref to point to those names. After DROP temp_*, those FKs are
    broken. This recreates the table with correct REFERENCES files(id), methods(id).
    Data in entity_cross_ref is dropped; cross-refs are rebuilt on next indexing.

    For migration code: use fix_entity_cross_ref_stale_fks_in_connection(conn) inside
    the same transaction before commit so the DB is never left broken.

    Args:
        db_path: Path to SQLite db file.
        timeout_seconds: Connection timeout.

    Returns:
        True if the table was recreated; False if no fix needed.
    """
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=timeout_seconds)
        try:
            fixed = fix_entity_cross_ref_stale_fks_in_connection(conn)
            if fixed:
                conn.commit()
            return fixed
        finally:
            conn.close()
    except Exception:
        return False


def corruption_marker_path(db_path: Path) -> Path:
    """Return path to persistent corruption marker for a SQLite db.

    Args:
        db_path: Path to SQLite db file.

    Returns:
        Path to marker JSON file.
    """
    return db_path.parent / f"{db_path.name}.corruption.json"


def read_corruption_marker(db_path: Path) -> Optional[dict[str, object]]:
    """Read corruption marker JSON if present.

    Args:
        db_path: Path to SQLite db file.

    Returns:
        Parsed marker dict if present and readable; otherwise None.
    """
    import json

    marker = corruption_marker_path(db_path)
    if not marker.exists():
        return None

    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data  # type: ignore[return-value]
        return {"raw": data}
    except Exception as e:
        return {"error": f"Failed to read marker: {e}", "path": str(marker)}


def write_corruption_marker(
    db_path: Path,
    *,
    message: str,
    backup_paths: tuple[str, ...] = (),
) -> str:
    """Write corruption marker JSON.

    Notes:
        Marker is used to keep the project in a "safe mode" where DB-dependent
        commands are blocked until explicit repair.

    Args:
        db_path: Path to SQLite db file.
        message: Human-readable corruption message.
        backup_paths: Backup paths created at detection time.

    Returns:
        Marker path as string.
    """
    import json

    marker = corruption_marker_path(db_path)
    payload = {
        "db_path": str(db_path),
        "detected_at": time.time(),
        "message": message,
        "backup_paths": list(backup_paths),
        "blocked": True,
    }
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(marker)


def clear_corruption_marker(db_path: Path) -> bool:
    """Remove corruption marker if present.

    Args:
        db_path: Path to SQLite db file.

    Returns:
        True if marker was removed; False if it did not exist.
    """
    marker = corruption_marker_path(db_path)
    if not marker.exists():
        return False
    try:
        marker.unlink()
        return True
    except Exception:
        return False
