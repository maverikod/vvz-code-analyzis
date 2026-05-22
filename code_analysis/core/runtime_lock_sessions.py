"""
Runtime process sessions and advisory file-lock leases.

This module owns the database state for cooperative file locks.  The OS-level
flock is handled by :mod:`code_analysis.core.file_lock`; this layer records
which registered runtime session owns a project file lease.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from code_analysis.core.sql_portable import sql_julian_timestamp_now_expr

logger = logging.getLogger(__name__)

RUNTIME_LOCK_SESSIONS_TABLE = "runtime_lock_sessions"
FILE_ADVISORY_LOCK_LEASES_TABLE = "file_advisory_lock_leases"

_session_lock = threading.Lock()
_current_session_id: Optional[str] = None
_current_session_pid: Optional[int] = None


@dataclass(frozen=True)
class RuntimeLockSession:
    """Registered runtime lock session for one OS process."""

    session_id: str
    pid: int
    role: str
    listener_url: Optional[str] = None
    hostname: Optional[str] = None


def normalize_lock_mode(lock_mode: str) -> str:
    """Normalize public lock-mode names to lease-table mode values."""
    raw = str(lock_mode or "").strip().lower()
    if raw in ("full", "exclusive", "ex", "lock_ex"):
        return "exclusive"
    if raw in ("block_write", "read_only", "shared", "sh", "lock_sh"):
        return "shared"
    if raw == "none":
        return "none"
    raise ValueError("lock_mode must be one of: none, block_write, full")


def lease_mode_to_public(mode: str) -> str:
    """Return API-facing mode from lease-table mode."""
    normalized = normalize_lock_mode(mode)
    if normalized == "exclusive":
        return "full"
    if normalized == "shared":
        return "block_write"
    return "none"


def _execute(database: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return database.execute(sql, params)


def _select_one(
    database: Any, sql: str, params: tuple[Any, ...] = ()
) -> Optional[Dict[str, Any]]:
    result = database.execute(sql, params)
    data = result.get("data") if isinstance(result, dict) else None
    if isinstance(data, list) and data:
        row = data[0]
        return dict(row) if isinstance(row, dict) else row
    return None


def _commit_best_effort(database: Any) -> None:
    commit = getattr(database, "commit", None)
    if callable(commit):
        try:
            commit()
        except Exception:
            logger.debug("Commit after runtime lock DML failed", exc_info=True)


def ensure_runtime_lock_tables(database: Any) -> None:
    """Create runtime session and advisory lease tables if schema sync has not run yet."""
    _execute(
        database,
        """
        CREATE TABLE IF NOT EXISTS runtime_lock_sessions (
            session_id TEXT PRIMARY KEY,
            pid INTEGER NOT NULL UNIQUE,
            listener_url TEXT,
            role TEXT NOT NULL,
            hostname TEXT,
            started_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now'))
        )
        """,
    )
    _execute(
        database,
        """
        CREATE TABLE IF NOT EXISTS file_advisory_lock_leases (
            session_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            lock_mode TEXT NOT NULL,
            locked_since REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            refcount INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (session_id, project_id, file_path, lock_mode),
            FOREIGN KEY (session_id) REFERENCES runtime_lock_sessions(session_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            CHECK (lock_mode IN ('exclusive', 'shared')),
            CHECK (refcount > 0)
        )
        """,
    )
    _execute(
        database,
        """
        CREATE INDEX IF NOT EXISTS idx_runtime_lock_sessions_pid
        ON runtime_lock_sessions(pid)
        """,
    )
    _execute(
        database,
        """
        CREATE INDEX IF NOT EXISTS idx_file_advisory_lock_leases_file
        ON file_advisory_lock_leases(project_id, file_path)
        """,
    )
    _execute(
        database,
        """
        CREATE INDEX IF NOT EXISTS idx_file_advisory_lock_leases_session
        ON file_advisory_lock_leases(session_id)
        """,
    )
    _commit_best_effort(database)


def register_runtime_session(
    database: Any,
    *,
    role: str,
    listener_url: Optional[str] = None,
    session_id: Optional[str] = None,
) -> RuntimeLockSession:
    """Register the current process and cache its session id."""
    global _current_session_id, _current_session_pid

    ensure_runtime_lock_tables(database)
    pid = os.getpid()
    sid = str(session_id or uuid.uuid4()).strip()
    role_s = str(role or "unknown").strip() or "unknown"
    host = socket.gethostname()
    _now = sql_julian_timestamp_now_expr(database)
    with _session_lock:
        _execute(database, "DELETE FROM runtime_lock_sessions WHERE pid = ?", (pid,))
        _execute(
            database,
            f"""
            INSERT INTO runtime_lock_sessions (
                session_id, pid, listener_url, role, hostname, started_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, {_now}, {_now})
            """,
            (sid, pid, listener_url, role_s, host),
        )
        _commit_best_effort(database)
        _current_session_id = sid
        _current_session_pid = pid
    logger.info(
        "Registered runtime lock session pid=%s session_id=%s role=%s", pid, sid, role_s
    )
    return RuntimeLockSession(
        session_id=sid,
        pid=pid,
        role=role_s,
        listener_url=listener_url,
        hostname=host,
    )


def get_cached_runtime_session_id() -> Optional[str]:
    """Return cached session id for the current process, if still valid."""
    with _session_lock:
        if _current_session_pid == os.getpid():
            return _current_session_id
    return None


def get_session_id_for_current_pid(database: Any, *, role: str = "command") -> str:
    """Resolve or register the runtime session for the current OS process."""
    cached = get_cached_runtime_session_id()
    if cached:
        return cached
    ensure_runtime_lock_tables(database)
    pid = os.getpid()
    row = _select_one(
        database,
        "SELECT session_id FROM runtime_lock_sessions WHERE pid = ? LIMIT 1",
        (pid,),
    )
    if row and row.get("session_id"):
        sid = str(row["session_id"])
        global _current_session_id, _current_session_pid
        with _session_lock:
            _current_session_id = sid
            _current_session_pid = pid
        return sid
    return register_runtime_session(database, role=role).session_id


def runtime_session_exists(database: Any, session_id: str) -> bool:
    """Return True when ``session_id`` is registered."""
    ensure_runtime_lock_tables(database)
    row = _select_one(
        database,
        "SELECT session_id FROM runtime_lock_sessions WHERE session_id = ? LIMIT 1",
        (str(session_id).strip(),),
    )
    return bool(row)


def ensure_client_lock_session(database: Any, client_session_id: str) -> str:
    """Register a ``client_sessions`` row for advisory lease FK (``runtime_lock_sessions``).

    Client sessions from ``session_create`` are independent of the daemon PID. This
    helper bridges them into ``runtime_lock_sessions`` so ``acquire_file_advisory_lease``
    and cooperative flocks can use the same ``session_id`` the client already holds.

    Args:
        database: Database client.
        client_session_id: UUID from ``session_create`` / ``client_sessions``.

    Returns:
        The normalized client session id.

    Raises:
        ValueError: when the session is missing from ``client_sessions`` or registration fails.
    """
    from code_analysis.core.client_sessions import is_session_valid

    sid = str(client_session_id).strip()
    if not sid:
        raise ValueError("client session_id is required")
    if not is_session_valid(database, sid):
        raise ValueError(f"client session not found: {sid}")
    if runtime_session_exists(database, sid):
        return sid

    ensure_runtime_lock_tables(database)
    _now = sql_julian_timestamp_now_expr(database)
    base_pid = -(uuid.UUID(sid).int % (2**31 - 1000)) - 1000
    host = socket.gethostname()
    for attempt in range(16):
        pid = base_pid - attempt
        occupied = _select_one(
            database,
            "SELECT session_id FROM runtime_lock_sessions WHERE pid = ? LIMIT 1",
            (pid,),
        )
        if occupied:
            continue
        try:
            _execute(
                database,
                f"""
                INSERT INTO runtime_lock_sessions (
                    session_id, pid, listener_url, role, hostname, started_at, updated_at
                )
                VALUES (?, ?, NULL, 'client', ?, {_now}, {_now})
                """,
                (sid, pid, host),
            )
            _commit_best_effort(database)
            logger.info(
                "Registered client lock session session_id=%s synthetic_pid=%s",
                sid,
                pid,
            )
            return sid
        except Exception:
            if runtime_session_exists(database, sid):
                return sid
            continue
    raise ValueError(f"could not register client lock session: {sid}")


def acquire_file_advisory_lease(
    database: Any,
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    lock_mode: str,
) -> Dict[str, Any]:
    """Insert or refcount-increment a file advisory lease."""
    ensure_runtime_lock_tables(database)
    sid = str(session_id).strip()
    pid = str(project_id).strip()
    rel = str(file_path).strip().replace("\\", "/")
    mode = normalize_lock_mode(lock_mode)
    if mode == "none":
        return {"success": True, "acquired": False, "lock_mode": "none"}
    if not runtime_session_exists(database, sid):
        raise ValueError(f"runtime lock session not found: {sid}")

    _now = sql_julian_timestamp_now_expr(database)
    row = _select_one(
        database,
        """
        SELECT refcount FROM file_advisory_lock_leases
        WHERE session_id = ? AND project_id = ? AND file_path = ? AND lock_mode = ?
        LIMIT 1
        """,
        (sid, pid, rel, mode),
    )
    if row:
        _execute(
            database,
            f"""
            UPDATE file_advisory_lock_leases
            SET refcount = refcount + 1, updated_at = {_now}
            WHERE session_id = ? AND project_id = ? AND file_path = ? AND lock_mode = ?
            """,
            (sid, pid, rel, mode),
        )
        refcount = int(row.get("refcount") or 0) + 1
    else:
        _execute(
            database,
            f"""
            INSERT INTO file_advisory_lock_leases (
                session_id, project_id, file_path, lock_mode, locked_since, updated_at, refcount
            )
            VALUES (?, ?, ?, ?, {_now}, {_now}, 1)
            """,
            (sid, pid, rel, mode),
        )
        refcount = 1
    _commit_best_effort(database)
    return {
        "success": True,
        "acquired": True,
        "session_id": sid,
        "project_id": pid,
        "file_path": rel,
        "lock_mode": lease_mode_to_public(mode),
        "refcount": refcount,
    }


def release_file_advisory_lease(
    database: Any,
    *,
    session_id: str,
    project_id: str,
    file_path: str,
    lock_mode: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Release or force-delete a file advisory lease."""
    ensure_runtime_lock_tables(database)
    sid = str(session_id).strip()
    pid = str(project_id).strip()
    rel = str(file_path).strip().replace("\\", "/")
    mode = normalize_lock_mode(lock_mode) if lock_mode else None

    params: list[Any] = [sid, pid, rel]
    where = "session_id = ? AND project_id = ? AND file_path = ?"
    if mode and mode != "none":
        where += " AND lock_mode = ?"
        params.append(mode)

    rows = database.execute(
        f"SELECT lock_mode, refcount FROM file_advisory_lock_leases WHERE {where}",
        tuple(params),
    )
    data = rows.get("data") if isinstance(rows, dict) else []
    lease_rows = list(data or [])
    if not lease_rows:
        return {
            "success": True,
            "released": False,
            "missing": True,
            "session_id": sid,
            "project_id": pid,
            "file_path": rel,
        }

    released = 0
    decremented = 0
    _now = sql_julian_timestamp_now_expr(database)
    for row in lease_rows:
        row_mode = str(row["lock_mode"])
        refcount = int(row.get("refcount") or 1)
        if force or refcount <= 1:
            _execute(
                database,
                """
                DELETE FROM file_advisory_lock_leases
                WHERE session_id = ? AND project_id = ? AND file_path = ? AND lock_mode = ?
                """,
                (sid, pid, rel, row_mode),
            )
            released += 1
        else:
            _execute(
                database,
                f"""
                UPDATE file_advisory_lock_leases
                SET refcount = refcount - 1, updated_at = {_now}
                WHERE session_id = ? AND project_id = ? AND file_path = ? AND lock_mode = ?
                """,
                (sid, pid, rel, row_mode),
            )
            decremented += 1
    _commit_best_effort(database)
    return {
        "success": True,
        "released": bool(released),
        "deleted_rows": released,
        "decremented_rows": decremented,
        "session_id": sid,
        "project_id": pid,
        "file_path": rel,
    }


def get_file_advisory_lock_status(
    database: Any,
    *,
    project_id: str,
    file_path: str,
) -> Dict[str, Any]:
    """
    Read-only aggregate of DB advisory leases for one project file.

    ``lock_status`` (API):

    - ``free`` — no active leases (Russian: свободен).
    - ``fully_locked`` — at least one ``exclusive`` lease with positive refcount
      (Russian: полностью заблокирован; no concurrent writers/readers via this layer).
    - ``write_locked`` — only ``shared`` leases (Russian: заблокирован для записи;
      readers may hold shared flock; writers should defer).

    Args:
        project_id: Project UUID.
        file_path: Path **relative to the registered watched project's** ``root_path``
            (POSIX), matching rows in ``file_advisory_lock_leases`` — not the analysis
            server's install root.

    Note:
        This reflects ``file_advisory_lock_leases`` only. OS ``flock`` on ``.lock``
        sidecars may differ if a process holds a lock without recording a lease.
    """
    ensure_runtime_lock_tables(database)
    pid = str(project_id).strip()
    rel = str(file_path).strip().replace("\\", "/")

    rows = database.execute(
        """
        SELECT session_id, lock_mode, refcount
        FROM file_advisory_lock_leases
        WHERE project_id = ? AND file_path = ?
        """,
        (pid, rel),
    )
    data = rows.get("data") if isinstance(rows, dict) else []
    leases_raw = list(data or [])

    exclusive_total = 0
    shared_total = 0
    exclusive_sessions: list[Dict[str, Any]] = []
    shared_sessions: list[Dict[str, Any]] = []

    for row in leases_raw:
        if not isinstance(row, dict):
            continue
        mode = str(row.get("lock_mode") or "")
        rc = max(0, int(row.get("refcount") or 0))
        sid = str(row.get("session_id") or "")
        if mode == "exclusive":
            exclusive_total += rc
            exclusive_sessions.append({"session_id": sid, "refcount": rc})
        elif mode == "shared":
            shared_total += rc
            shared_sessions.append({"session_id": sid, "refcount": rc})

    if exclusive_total > 0:
        lock_status = "fully_locked"
    elif shared_total > 0:
        lock_status = "write_locked"
    else:
        lock_status = "free"

    return {
        "success": True,
        "project_id": pid,
        "file_path": rel,
        "lock_status": lock_status,
        "leases": {
            "exclusive_total_refcount": exclusive_total,
            "shared_total_refcount": shared_total,
            "exclusive_sessions": exclusive_sessions,
            "shared_sessions": shared_sessions,
        },
    }


def release_all_leases_for_session(database: Any, session_id: str) -> int:
    """Remove all advisory lease rows for ``session_id``."""
    ensure_runtime_lock_tables(database)
    rows = database.execute(
        "SELECT COUNT(*) AS count FROM file_advisory_lock_leases WHERE session_id = ?",
        (str(session_id).strip(),),
    )
    data = rows.get("data") if isinstance(rows, dict) else []
    count = int((data or [{"count": 0}])[0].get("count") or 0)
    _execute(
        database,
        "DELETE FROM file_advisory_lock_leases WHERE session_id = ?",
        (str(session_id).strip(),),
    )
    _commit_best_effort(database)
    return count
