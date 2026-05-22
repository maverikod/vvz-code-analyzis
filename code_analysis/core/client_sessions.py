"""
Client session persistence layer: DDL constants, migration function, and domain exceptions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from code_analysis.core.database_client.client import DatabaseClient

logger = logging.getLogger(__name__)

CLIENT_SESSIONS_TABLE: str = "client_sessions"
SESSION_FILE_LOCKS_TABLE: str = "session_file_locks"
ROLES_TABLE: str = "roles"
ROLE_PERMISSIONS_TABLE: str = "role_permissions"
SESSION_ROLES_TABLE: str = "session_roles"

CLIENT_SESSIONS_DDL: str = (
    "CREATE TABLE IF NOT EXISTS client_sessions (session_id TEXT PRIMARY KEY, "
    "comment TEXT NOT NULL DEFAULT '', created_at REAL DEFAULT (julianday('now')), "
    "last_active_at REAL DEFAULT (julianday('now')))"
)
CLIENT_SESSIONS_IDX: str = (
    "CREATE INDEX IF NOT EXISTS idx_client_sessions_last_active "
    "ON client_sessions(last_active_at)"
)
SESSION_FILE_LOCKS_DDL: str = (
    "CREATE TABLE IF NOT EXISTS session_file_locks (session_id TEXT NOT NULL, "
    "project_id TEXT NOT NULL, file_id TEXT NOT NULL, "
    "locked_at REAL DEFAULT (julianday('now')), "
    "PRIMARY KEY (session_id, project_id, file_id), "
    "FOREIGN KEY (session_id) REFERENCES client_sessions(session_id) ON DELETE CASCADE, "
    "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE, "
    "FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE)"
)
SESSION_FILE_LOCKS_IDX_SESSION: str = (
    "CREATE INDEX IF NOT EXISTS idx_session_file_locks_session "
    "ON session_file_locks(session_id)"
)
SESSION_FILE_LOCKS_IDX_FILE: str = (
    "CREATE INDEX IF NOT EXISTS idx_session_file_locks_file "
    "ON session_file_locks(project_id, file_id)"
)
ROLES_DDL: str = (
    "CREATE TABLE IF NOT EXISTS roles (role_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL)"
)
ROLE_PERMISSIONS_DDL: str = (
    "CREATE TABLE IF NOT EXISTS role_permissions (role_id TEXT NOT NULL, "
    "command_name TEXT NOT NULL, server_uuid TEXT NOT NULL, "
    "PRIMARY KEY (role_id, command_name, server_uuid), "
    "FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE)"
)
ROLE_PERMISSIONS_IDX: str = (
    "CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id)"
)
SESSION_ROLES_DDL: str = (
    "CREATE TABLE IF NOT EXISTS session_roles (session_id TEXT NOT NULL, role_id TEXT NOT NULL, "
    "PRIMARY KEY (session_id, role_id), "
    "FOREIGN KEY (session_id) REFERENCES client_sessions(session_id) ON DELETE CASCADE, "
    "FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE)"
)


class SessionNotFoundError(ValueError):
    """Raised when session_id is not found in client_sessions."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: {session_id}")
        self.session_id = session_id


class SessionHasLocksError(ValueError):
    """Raised when a session has open file locks and force=False."""

    def __init__(self, session_id: str, lock_count: int) -> None:
        msg = f"Session {session_id} has {lock_count} open file lock(s). Use force=True to release."
        super().__init__(msg)
        self.session_id = session_id
        self.lock_count = lock_count


class SessionHasSubordinatesError(ValueError):
    """Raised when a session has subordinate links and force=False."""

    def __init__(self, session_id: str, subordinate_count: int) -> None:
        msg = (
            f"Session {session_id} has {subordinate_count} subordinate session link(s). "
            "Use force=True to delete them."
        )
        super().__init__(msg)
        self.session_id = session_id
        self.subordinate_count = subordinate_count


def ensure_client_session_tables(conn: Any) -> None:
    """
    Create all client-session-related tables and indexes idempotently.

    Runs CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS for all five
    tables (client_sessions, session_file_locks, roles, role_permissions,
    session_roles). Commits after all statements succeed. Rolls back and logs
    a warning on any exception without re-raising (same pattern as the existing
    ensure_* functions in sqlite_migrations.py).

    Args:
        conn: An active SQLite connection object with .execute(), .commit(),
            and .rollback() methods. If falsy, returns immediately.
    """
    if not conn:
        return
    try:
        conn.execute(CLIENT_SESSIONS_DDL)
        conn.execute(CLIENT_SESSIONS_IDX)
        conn.execute(SESSION_FILE_LOCKS_DDL)
        conn.execute(SESSION_FILE_LOCKS_IDX_SESSION)
        conn.execute(SESSION_FILE_LOCKS_IDX_FILE)
        conn.execute(ROLES_DDL)
        conn.execute(ROLE_PERMISSIONS_DDL)
        conn.execute(ROLE_PERMISSIONS_IDX)
        conn.execute(SESSION_ROLES_DDL)
        conn.commit()
    except Exception as e:
        logger.warning("Could not ensure client session tables: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def create_client_session(
    database: DatabaseClient,
    comment: str,
    role_ids: Optional[list[str]] = None,
) -> dict[str, object]:
    """
    Create a new client session and assign roles.

    Inserts a row into client_sessions with a server-generated UUID4 session_id.
    If role_ids is provided and non-empty, inserts rows into session_roles for
    each role_id. All inserts are wrapped in a single transaction: if any insert
    fails the entire operation is rolled back and the exception is re-raised.

    Args:
        database: DatabaseClient instance.
        comment: Human-readable label for the session. May be empty string.
        role_ids: Optional list of role UUID4 strings to assign at creation.

    Returns:
        dict with keys: session_id (str), comment (str), created_at (float),
        last_active_at (float).
    """
    session_id = str(uuid.uuid4())
    tid = database.begin_transaction()
    try:
        database.execute(
            "INSERT INTO client_sessions (session_id, comment) VALUES (?, ?)",
            (session_id, comment),
        )
        if role_ids:
            for role_id in role_ids:
                database.execute(
                    "INSERT INTO session_roles (session_id, role_id) VALUES (?, ?)",
                    (session_id, role_id),
                )
        database.commit_transaction(tid)
    except Exception:
        try:
            database.rollback_transaction(tid)
        except Exception:
            pass
        raise
    res = database.execute(
        "SELECT session_id, comment, created_at, last_active_at FROM client_sessions WHERE session_id = ?",
        (session_id,),
    )
    return dict(res["data"][0])


def get_client_session(
    database: DatabaseClient,
    session_id: str,
) -> Optional[dict[str, object]]:
    """
    Fetch one client session by primary key.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Returns:
        dict with keys session_id, comment, created_at, last_active_at,
        or None if not found.
    """
    res = database.execute(
        "SELECT session_id, comment, created_at, last_active_at FROM client_sessions WHERE session_id = ?",
        (session_id,),
    )
    data = res.get("data") or []
    return dict(data[0]) if data else None


def is_session_valid(
    database: DatabaseClient,
    session_id: str,
) -> bool:
    """
    Return True if session_id exists in client_sessions, False otherwise.

    No side effects: last_active_at is NOT updated.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Returns:
        True if the session exists, False otherwise.
    """
    res = database.execute(
        "SELECT 1 FROM client_sessions WHERE session_id = ? LIMIT 1",
        (session_id,),
    )
    return bool(res.get("data"))


def touch_client_session(
    database: DatabaseClient,
    session_id: str,
) -> bool:
    """
    Update last_active_at to now for the given session.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Returns:
        True if the session was found and updated, False if not found.
    """
    res = database.execute(
        "UPDATE client_sessions SET last_active_at = julianday('now') WHERE session_id = ?",
        (session_id,),
    )
    return (res.get("affected_rows") or 0) > 0


def touch_or_error(
    database: DatabaseClient,
    session_id: str,
) -> None:
    """
    Update last_active_at or raise SessionNotFoundError.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Raises:
        SessionNotFoundError: if session_id is not found in client_sessions.
    """
    if not touch_client_session(database, session_id):
        raise SessionNotFoundError(session_id)


def list_client_sessions(
    database: DatabaseClient,
    stale_threshold_seconds: Optional[int] = None,
) -> list[dict[str, object]]:
    """
    List all client sessions, optionally filtered by inactivity threshold.

    Args:
        database: DatabaseClient instance.
        stale_threshold_seconds: If provided, return only sessions whose
            last_active_at is older than this many seconds. Must be >= 1.

    Returns:
        List of dicts with keys: session_id, comment, created_at,
        last_active_at. Ordered by last_active_at ascending.
    """
    if stale_threshold_seconds is not None:
        threshold_days = stale_threshold_seconds / 86400.0
        res = database.execute(
            "SELECT session_id, comment, created_at, last_active_at "
            "FROM client_sessions "
            "WHERE julianday('now') - last_active_at > ? "
            "ORDER BY last_active_at ASC",
            (threshold_days,),
        )
    else:
        res = database.execute(
            "SELECT session_id, comment, created_at, last_active_at "
            "FROM client_sessions ORDER BY last_active_at ASC"
        )
    return [dict(row) for row in (res.get("data") or [])]


def delete_client_session(
    database: DatabaseClient,
    session_id: str,
    force: bool = False,
) -> dict[str, object]:
    """
    Delete a client session, optionally force-releasing locks and subordinates.

    If force is False, raises SessionHasLocksError when file locks exist and
    SessionHasSubordinatesError when subordinate session links exist (this session
    is the parent).

    If force is True, recursively deletes all linked subordinate client sessions
    first (each with force=True), then releases file locks on this session, then
    deletes the session row.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.
        force: If True, delete subordinates and release locks before deleting.

    Returns:
        dict with keys: session_id (str), deleted (bool, always True),
        released_lock_count (int), released_subordinate_count (int).

    Raises:
        SessionNotFoundError: if session_id is not found.
        SessionHasLocksError: if force is False and open locks exist.
        SessionHasSubordinatesError: if force is False and subordinate links exist.
    """
    from code_analysis.core.subordinate_sessions import (
        count_subordinate_links_for_parent,
        list_subordinate_session_ids_for_parent,
    )

    if get_client_session(database, session_id) is None:
        raise SessionNotFoundError(session_id)
    res = database.execute(
        "SELECT COUNT(*) as cnt FROM session_file_locks WHERE session_id = ?",
        (session_id,),
    )
    data = res.get("data") or []
    lock_count: int = data[0]["cnt"] if data else 0
    subordinate_count = count_subordinate_links_for_parent(database, session_id)
    if not force:
        if lock_count > 0:
            raise SessionHasLocksError(session_id, lock_count)
        if subordinate_count > 0:
            raise SessionHasSubordinatesError(session_id, subordinate_count)

    released_subordinates = 0
    if force and subordinate_count > 0:
        for sub_id in list_subordinate_session_ids_for_parent(database, session_id):
            sub_result = delete_client_session(database, sub_id, force=True)
            released_subordinates += 1
            released_subordinates += int(
                sub_result.get("released_subordinate_count") or 0
            )

    released = 0
    if force and lock_count > 0:
        res2 = database.execute(
            "DELETE FROM session_file_locks WHERE session_id = ?",
            (session_id,),
        )
        released = res2.get("affected_rows") or 0
    database.execute(
        "DELETE FROM client_sessions WHERE session_id = ?",
        (session_id,),
    )
    return {
        "session_id": session_id,
        "deleted": True,
        "released_lock_count": released,
        "released_subordinate_count": released_subordinates,
    }


def open_session_file(
    database: DatabaseClient,
    session_id: str,
    project_id: str,
    file_id: str,
) -> dict[str, object]:
    """
    Acquire a file lock for a session (idempotent).

    Inserts a row into session_file_locks when absent (idempotent).

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string of the owning session.
        project_id: UUID4 string of the registered project.
        file_id: UUID4 string of the file record.

    Returns:
        dict with keys: acquired (bool, True if new row inserted, False if
        lock already existed), session_id (str), project_id (str), file_id (str).
    """
    existing = database.execute(
        "SELECT 1 AS present FROM session_file_locks "
        "WHERE session_id = ? AND project_id = ? AND file_id = ? LIMIT 1",
        (session_id, project_id, file_id),
    )
    if existing.get("data"):
        return {
            "acquired": False,
            "session_id": session_id,
            "project_id": project_id,
            "file_id": file_id,
        }
    res = database.execute(
        "INSERT INTO session_file_locks (session_id, project_id, file_id) VALUES (?, ?, ?)",
        (session_id, project_id, file_id),
    )
    return {
        "acquired": (res.get("affected_rows") or 0) > 0,
        "session_id": session_id,
        "project_id": project_id,
        "file_id": file_id,
    }


def close_session_file(
    database: DatabaseClient,
    session_id: str,
    project_id: str,
    file_id: str,
) -> dict[str, object]:
    """
    Release a file lock for a session (idempotent).

    Deletes the row from session_file_locks matching the primary key triple.
    If no row exists, was_locked is False but the call still succeeds.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string of the owning session.
        project_id: UUID4 string of the registered project.
        file_id: UUID4 string of the file record.

    Returns:
        dict with keys: released (bool, True if row deleted), was_locked (bool,
        True if the lock existed before this call), session_id, project_id, file_id.
    """
    res = database.execute(
        "DELETE FROM session_file_locks WHERE session_id = ? AND project_id = ? AND file_id = ?",
        (session_id, project_id, file_id),
    )
    was_locked = (res.get("affected_rows") or 0) > 0
    return {
        "released": was_locked,
        "was_locked": was_locked,
        "session_id": session_id,
        "project_id": project_id,
        "file_id": file_id,
    }


def list_session_file_locks(
    database: DatabaseClient,
    session_id: str,
) -> list[dict[str, object]]:
    """
    List all file locks held by a session.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Returns:
        List of dicts with keys: project_id (str), file_id (str),
        locked_at (float). Ordered by locked_at ascending.
    """
    res = database.execute(
        "SELECT project_id, file_id, locked_at FROM session_file_locks "
        "WHERE session_id = ? ORDER BY locked_at ASC",
        (session_id,),
    )
    return [dict(row) for row in (res.get("data") or [])]


def count_session_file_locks(
    database: DatabaseClient,
    session_id: str,
) -> int:
    """
    Count open file locks for a session.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Returns:
        Integer count of open locks for this session.
    """
    res = database.execute(
        "SELECT COUNT(*) as cnt FROM session_file_locks WHERE session_id = ?",
        (session_id,),
    )
    data = res.get("data") or []
    return data[0]["cnt"] if data else 0


def list_locked_files(
    database: DatabaseClient,
) -> list[dict[str, object]]:
    """
    List all locked files across all sessions.

    session_id is intentionally NOT included in the output. This function
    is used by the CLI operator interface (casmgr locks) where session
    attribution must not be shown.

    Args:
        database: DatabaseClient instance.

    Returns:
        List of dicts with keys: project_id (str), file_id (str),
        locked_at (float). Ordered by project_id, file_id ascending.
    """
    res = database.execute(
        "SELECT project_id, file_id, locked_at FROM session_file_locks "
        "ORDER BY project_id ASC, file_id ASC"
    )
    return [dict(row) for row in (res.get("data") or [])]


def list_roles(
    database: DatabaseClient,
) -> list[dict[str, object]]:
    """
    List all defined roles.

    Args:
        database: DatabaseClient instance.

    Returns:
        List of dicts with keys: role_id (str), name (str).
        Ordered by name ascending.
    """
    res = database.execute("SELECT role_id, name FROM roles ORDER BY name ASC")
    return [dict(row) for row in (res.get("data") or [])]


def get_roles_for_session(
    database: DatabaseClient,
    session_id: str,
) -> list[dict[str, object]]:
    """
    Get all roles assigned to a session.

    Args:
        database: DatabaseClient instance.
        session_id: UUID4 string.

    Returns:
        List of dicts with keys: role_id (str), name (str).
        Ordered by name ascending.
    """
    res = database.execute(
        "SELECT r.role_id, r.name FROM roles r "
        "JOIN session_roles sr ON r.role_id = sr.role_id "
        "WHERE sr.session_id = ? ORDER BY r.name ASC",
        (session_id,),
    )
    return [dict(row) for row in (res.get("data") or [])]


def get_permissions_for_roles(
    database: DatabaseClient,
    role_ids: list[str],
    server_uuid: str,
) -> list[str]:
    """
    Get all command names permitted for the given roles on a specific server.

    Returns the union of all command_name values from role_permissions where
    role_id is in role_ids and server_uuid matches. Used by the SecurityPolicy
    evaluator to determine allowed commands.

    Args:
        database: DatabaseClient instance.
        role_ids: List of role UUID4 strings. If empty, returns empty list.
        server_uuid: UUID4 string of the proxy server.

    Returns:
        List of distinct command_name strings. Order is not guaranteed.
    """
    if not role_ids:
        return []
    placeholders = ",".join("?" * len(role_ids))
    res = database.execute(
        f"SELECT DISTINCT command_name FROM role_permissions "
        f"WHERE role_id IN ({placeholders}) AND server_uuid = ?",
        (*role_ids, server_uuid),
    )
    return [row["command_name"] for row in (res.get("data") or [])]
