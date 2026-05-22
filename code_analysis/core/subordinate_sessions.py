"""
Subordinate client session links: parent session, child session, server instance.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from code_analysis.core.client_sessions import (
    SessionNotFoundError,
    is_session_valid,
)
from code_analysis.core.uuid_validation import is_valid_uuid4

if TYPE_CHECKING:
    from code_analysis.core.database_client.client import DatabaseClient

logger = logging.getLogger(__name__)

SUBORDINATE_SESSIONS_TABLE: str = "subordinate_sessions"

SUBORDINATE_SESSIONS_DDL: str = (
    "CREATE TABLE IF NOT EXISTS subordinate_sessions ("
    "parent_session_id TEXT NOT NULL, "
    "subordinate_session_id TEXT NOT NULL, "
    "server_uuid TEXT NOT NULL, "
    "comment TEXT NOT NULL DEFAULT '', "
    "PRIMARY KEY (parent_session_id, subordinate_session_id, server_uuid), "
    "FOREIGN KEY (parent_session_id) REFERENCES client_sessions(session_id) "
    "ON DELETE CASCADE, "
    "FOREIGN KEY (subordinate_session_id) REFERENCES client_sessions(session_id) "
    "ON DELETE CASCADE)"
)
SUBORDINATE_SESSIONS_IDX_PARENT: str = (
    "CREATE INDEX IF NOT EXISTS idx_subordinate_sessions_parent "
    "ON subordinate_sessions(parent_session_id)"
)
SUBORDINATE_SESSIONS_IDX_SUBORDINATE: str = (
    "CREATE INDEX IF NOT EXISTS idx_subordinate_sessions_subordinate "
    "ON subordinate_sessions(subordinate_session_id)"
)
SUBORDINATE_SESSIONS_IDX_SERVER: str = (
    "CREATE INDEX IF NOT EXISTS idx_subordinate_sessions_server "
    "ON subordinate_sessions(server_uuid)"
)

_SELECT_COLUMNS = "parent_session_id, subordinate_session_id, server_uuid, comment"


class SubordinateSessionNotFoundError(ValueError):
    """Raised when a subordinate session link row is missing."""

    def __init__(
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
    ) -> None:
        super().__init__(
            "Subordinate session link not found: "
            f"parent={parent_session_id!r}, "
            f"subordinate={subordinate_session_id!r}, "
            f"server={server_uuid!r}"
        )
        self.parent_session_id = parent_session_id
        self.subordinate_session_id = subordinate_session_id
        self.server_uuid = server_uuid


class SubordinateSessionAlreadyExistsError(ValueError):
    """Raised when creating a duplicate subordinate session link."""

    def __init__(
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
    ) -> None:
        super().__init__(
            "Subordinate session link already exists: "
            f"parent={parent_session_id!r}, "
            f"subordinate={subordinate_session_id!r}, "
            f"server={server_uuid!r}"
        )
        self.parent_session_id = parent_session_id
        self.subordinate_session_id = subordinate_session_id
        self.server_uuid = server_uuid


def ensure_subordinate_session_tables(conn: Any) -> None:
    """
    Create subordinate_sessions table and indexes idempotently.

    Args:
        conn: SQLite connection with execute/commit/rollback.
    """
    if not conn:
        return
    try:
        conn.execute(SUBORDINATE_SESSIONS_DDL)
        conn.execute(SUBORDINATE_SESSIONS_IDX_PARENT)
        conn.execute(SUBORDINATE_SESSIONS_IDX_SUBORDINATE)
        conn.execute(SUBORDINATE_SESSIONS_IDX_SERVER)
        conn.commit()
    except Exception as e:
        logger.warning("Could not ensure subordinate session tables: %s", e)
        try:
            conn.rollback()
        except Exception:
            pass


def _normalize_key(
    parent_session_id: str,
    subordinate_session_id: str,
    server_uuid: str,
) -> tuple[str, str, str]:
    parent = str(parent_session_id or "").strip()
    subordinate = str(subordinate_session_id or "").strip()
    server = str(server_uuid or "").strip()
    if not is_valid_uuid4(parent):
        raise ValueError("parent_session_id must be a valid UUID4")
    if not is_valid_uuid4(subordinate):
        raise ValueError("subordinate_session_id must be a valid UUID4")
    if not is_valid_uuid4(server):
        raise ValueError("server_uuid must be a valid UUID4")
    if parent == subordinate:
        raise ValueError("parent_session_id and subordinate_session_id must differ")
    return parent, subordinate, server


def _row_from_data(data: list[Any]) -> Optional[dict[str, object]]:
    if not data:
        return None
    return dict(data[0])


def create_subordinate_session(
    database: DatabaseClient,
    *,
    parent_session_id: str,
    subordinate_session_id: str,
    server_uuid: str,
    comment: str = "",
) -> dict[str, object]:
    """
    Link a subordinate client session to a parent session on a server.

    Args:
        database: Database client.
        parent_session_id: Leading session UUID4.
        subordinate_session_id: Subordinate session UUID4.
        server_uuid: Server instance UUID4.
        comment: Human-readable label.

    Returns:
        Row dict with parent_session_id, subordinate_session_id, server_uuid, comment.

    Raises:
        ValueError: invalid UUIDs or parent equals subordinate.
        SessionNotFoundError: parent or subordinate missing from client_sessions.
        SubordinateSessionAlreadyExistsError: duplicate composite key.
    """
    parent, subordinate, server = _normalize_key(
        parent_session_id, subordinate_session_id, server_uuid
    )
    if not is_session_valid(database, parent):
        raise SessionNotFoundError(parent)
    if not is_session_valid(database, subordinate):
        raise SessionNotFoundError(subordinate)
    if get_subordinate_session(
        database,
        parent_session_id=parent,
        subordinate_session_id=subordinate,
        server_uuid=server,
    ):
        raise SubordinateSessionAlreadyExistsError(parent, subordinate, server)
    database.execute(
        "INSERT INTO subordinate_sessions "
        "(parent_session_id, subordinate_session_id, server_uuid, comment) "
        "VALUES (?, ?, ?, ?)",
        (parent, subordinate, server, str(comment or "")),
    )
    row = get_subordinate_session(
        database,
        parent_session_id=parent,
        subordinate_session_id=subordinate,
        server_uuid=server,
    )
    assert row is not None
    return row


def get_subordinate_session(
    database: DatabaseClient,
    *,
    parent_session_id: str,
    subordinate_session_id: str,
    server_uuid: str,
) -> Optional[dict[str, object]]:
    """Fetch one subordinate session link by composite primary key."""
    parent, subordinate, server = _normalize_key(
        parent_session_id, subordinate_session_id, server_uuid
    )
    res = database.execute(
        f"SELECT {_SELECT_COLUMNS} FROM subordinate_sessions "
        "WHERE parent_session_id = ? AND subordinate_session_id = ? "
        "AND server_uuid = ?",
        (parent, subordinate, server),
    )
    return _row_from_data(res.get("data") or [])


def update_subordinate_session(
    database: DatabaseClient,
    *,
    parent_session_id: str,
    subordinate_session_id: str,
    server_uuid: str,
    comment: str,
) -> dict[str, object]:
    """
    Update comment on an existing subordinate session link.

    Raises:
        SubordinateSessionNotFoundError: row absent.
    """
    parent, subordinate, server = _normalize_key(
        parent_session_id, subordinate_session_id, server_uuid
    )
    res = database.execute(
        "UPDATE subordinate_sessions SET comment = ? "
        "WHERE parent_session_id = ? AND subordinate_session_id = ? "
        "AND server_uuid = ?",
        (str(comment or ""), parent, subordinate, server),
    )
    if (res.get("affected_rows") or 0) < 1:
        raise SubordinateSessionNotFoundError(parent, subordinate, server)
    row = get_subordinate_session(
        database,
        parent_session_id=parent,
        subordinate_session_id=subordinate,
        server_uuid=server,
    )
    assert row is not None
    return row


def delete_subordinate_session(
    database: DatabaseClient,
    *,
    parent_session_id: str,
    subordinate_session_id: str,
    server_uuid: str,
) -> dict[str, object]:
    """
    Delete one subordinate session link.

    Returns:
        dict with parent_session_id, subordinate_session_id, server_uuid, deleted=True.

    Raises:
        SubordinateSessionNotFoundError: row absent.
    """
    parent, subordinate, server = _normalize_key(
        parent_session_id, subordinate_session_id, server_uuid
    )
    res = database.execute(
        "DELETE FROM subordinate_sessions "
        "WHERE parent_session_id = ? AND subordinate_session_id = ? "
        "AND server_uuid = ?",
        (parent, subordinate, server),
    )
    if (res.get("affected_rows") or 0) < 1:
        raise SubordinateSessionNotFoundError(parent, subordinate, server)
    return {
        "parent_session_id": parent,
        "subordinate_session_id": subordinate,
        "server_uuid": server,
        "deleted": True,
    }


def list_subordinate_sessions(
    database: DatabaseClient,
    *,
    parent_session_id: Optional[str] = None,
    subordinate_session_id: Optional[str] = None,
    server_uuid: Optional[str] = None,
) -> list[dict[str, object]]:
    """
    List subordinate session links with optional filters.

    Each filter, when provided, must be a valid UUID4 string.
    """
    clauses: list[str] = []
    params: list[str] = []
    if parent_session_id is not None:
        parent = str(parent_session_id).strip()
        if not is_valid_uuid4(parent):
            raise ValueError("parent_session_id must be a valid UUID4")
        clauses.append("parent_session_id = ?")
        params.append(parent)
    if subordinate_session_id is not None:
        subordinate = str(subordinate_session_id).strip()
        if not is_valid_uuid4(subordinate):
            raise ValueError("subordinate_session_id must be a valid UUID4")
        clauses.append("subordinate_session_id = ?")
        params.append(subordinate)
    if server_uuid is not None:
        server = str(server_uuid).strip()
        if not is_valid_uuid4(server):
            raise ValueError("server_uuid must be a valid UUID4")
        clauses.append("server_uuid = ?")
        params.append(server)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    res = database.execute(
        f"SELECT {_SELECT_COLUMNS} FROM subordinate_sessions{where} "
        "ORDER BY parent_session_id ASC, server_uuid ASC, subordinate_session_id ASC",
        tuple(params),
    )
    return [dict(row) for row in (res.get("data") or [])]


def count_subordinate_links_for_parent(
    database: DatabaseClient,
    parent_session_id: str,
) -> int:
    """Count subordinate session links where ``parent_session_id`` is the parent."""
    res = database.execute(
        "SELECT COUNT(*) AS cnt FROM subordinate_sessions WHERE parent_session_id = ?",
        (str(parent_session_id).strip(),),
    )
    data = res.get("data") or []
    return int(data[0]["cnt"]) if data else 0


def list_subordinate_session_ids_for_parent(
    database: DatabaseClient,
    parent_session_id: str,
) -> list[str]:
    """Return distinct subordinate session IDs linked to a parent session."""
    res = database.execute(
        "SELECT DISTINCT subordinate_session_id FROM subordinate_sessions "
        "WHERE parent_session_id = ? ORDER BY subordinate_session_id ASC",
        (str(parent_session_id).strip(),),
    )
    return [str(row["subordinate_session_id"]) for row in (res.get("data") or [])]
