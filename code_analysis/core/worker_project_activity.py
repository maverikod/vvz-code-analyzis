"""
Project-scoped activity lease coordinator (watcher / indexer / command).

Uses table ``project_activity_locks`` only. Callers must not embed raw SQL for
this table; use the public API below.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Final, Optional, Set, cast

logger = logging.getLogger(__name__)

_LOG_PREFIX: Final[str] = "[WORKER_COORD]"

TABLE: Final[str] = "project_activity_locks"

ALLOWED_OWNER_TYPES: Final[Set[str]] = {"watcher", "indexer", "command"}
ALLOWED_ACTIVITIES: Final[Set[str]] = {
    "watcher_staging",
    "watcher_inserting_new_files",
    "watcher_updating_changed_files",
    "watcher_marking_deleted_files",
    "watcher_queueing",
    "indexer_processing",
    "command_mutation",
}

_ACQUIRE_SQL = (
    f"INSERT INTO {TABLE} "
    "(project_id, owner_type, owner_id, activity, acquired_at, heartbeat_at, lease_until) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) "
    f"ON CONFLICT(project_id) DO UPDATE SET "
    "owner_type = excluded.owner_type, "
    "owner_id = excluded.owner_id, "
    "activity = excluded.activity, "
    "heartbeat_at = excluded.heartbeat_at, "
    "lease_until = excluded.lease_until, "
    "acquired_at = CASE "
    f"WHEN {TABLE}.lease_until < ? THEN excluded.acquired_at "
    f"WHEN {TABLE}.owner_type = excluded.owner_type "
    f"AND {TABLE}.owner_id = excluded.owner_id "
    f"THEN {TABLE}.acquired_at "
    "ELSE excluded.acquired_at "
    "END "
    f"WHERE ({TABLE}.lease_until < ?) OR "
    f"({TABLE}.owner_type = excluded.owner_type AND {TABLE}.owner_id = excluded.owner_id)"
)

_HEARTBEAT_SQL = (
    f"UPDATE {TABLE} SET activity = ?, heartbeat_at = ?, lease_until = ? "
    "WHERE project_id = ? AND owner_type = ? AND owner_id = ? AND lease_until >= ?"
)

_RELEASE_SQL = (
    f"DELETE FROM {TABLE} WHERE project_id = ? AND owner_type = ? AND owner_id = ?"
)


def _validate_project_id(project_id: str) -> None:
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id must be a non-empty string")


def _validate_owner_type(owner_type: str) -> None:
    if owner_type not in ALLOWED_OWNER_TYPES:
        raise ValueError(
            f"invalid owner_type: {owner_type!r}; allowed: {sorted(ALLOWED_OWNER_TYPES)}"
        )


def _validate_activity(activity: str) -> None:
    if activity not in ALLOWED_ACTIVITIES:
        raise ValueError(
            f"invalid activity: {activity!r}; allowed: {sorted(ALLOWED_ACTIVITIES)}"
        )


def _validate_ttl(ttl_seconds: float) -> None:
    if not isinstance(ttl_seconds, (int, float)) or float(ttl_seconds) <= 0:
        raise ValueError("ttl_seconds must be a positive number")


def _validate_owner_id(owner_id: str) -> None:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("owner_id must be a non-empty string")


def _affected(result: Dict[str, Any]) -> int:
    n = result.get("affected_rows", 0)
    try:
        return int(n) if n is not None and int(n) >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _execute_coord(
    database: Any,
    sql: str,
    params: Optional[tuple],
    *,
    transaction_id: Optional[str],
    rpc_priority: int,
) -> Dict[str, Any]:
    """``database.execute`` with optional RPC priority when the object supports it."""
    if rpc_priority:
        try:
            return cast(
                Dict[str, Any],
                database.execute(
                    sql,
                    params,
                    transaction_id=transaction_id,
                    priority=rpc_priority,
                ),
            )
        except TypeError:
            pass
    return cast(
        Dict[str, Any],
        database.execute(sql, params, transaction_id=transaction_id),
    )


def _select_coord_lock_row(
    database: Any,
    project_id: str,
    *,
    rpc_priority: int,
) -> Optional[Dict[str, Any]]:
    if rpc_priority:
        try:
            rows = database.select(
                TABLE,
                where={"project_id": project_id},
                priority=rpc_priority,
            )
        except TypeError:
            rows = database.select(
                TABLE,
                where={"project_id": project_id},
            )
    else:
        rows = database.select(
            TABLE,
            where={"project_id": project_id},
        )
    if not rows:
        return None
    return cast(Dict[str, Any], dict(rows[0]))


def _fetch_lock_row(
    database: Any, project_id: str, *, rpc_priority: int = 0
) -> Optional[Dict[str, Any]]:
    return _select_coord_lock_row(database, project_id, rpc_priority=rpc_priority)


def _log_coord(
    op: str,
    *,
    project_id: str,
    owner_type: str,
    owner_id: str,
    activity: str,
    result: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    base = (
        f"{_LOG_PREFIX} op={op} project_id={project_id!r} owner_type={owner_type!r} "
        f"owner_id={owner_id!r} activity={activity!r} result={result!r}"
    )
    if extra:
        parts = [f"{k}={v!r}" for k, v in extra.items() if v is not None]
        if parts:
            base = base + " " + " ".join(parts)
    logger.info(base)


def try_acquire_project_activity(
    database: Any,
    project_id: str,
    owner_type: str,
    owner_id: str,
    activity: str,
    ttl_seconds: float,
    *,
    rpc_priority: int = 0,
) -> bool:
    """Atomically take or refresh the project lease, or return False if busy.

    See Step 13 lease rules. Uses a single upsert (PostgreSQL) or equivalent
    semantics on SQLite. ``time.time()`` defines epoch seconds for timestamps.
    """
    _validate_project_id(project_id)
    _validate_owner_type(owner_type)
    _validate_owner_id(owner_id)
    _validate_activity(activity)
    _validate_ttl(ttl_seconds)

    now = time.time()
    lease_until = now + float(ttl_seconds)
    params = (
        project_id,
        owner_type,
        owner_id,
        activity,
        now,
        now,
        lease_until,
        now,
        now,
    )
    res = _execute_coord(
        database,
        _ACQUIRE_SQL,
        params,
        transaction_id=None,
        rpc_priority=rpc_priority,
    )
    ok = _affected(res) > 0
    if ok:
        _log_coord(
            "try_acquire",
            project_id=project_id,
            owner_type=owner_type,
            owner_id=owner_id,
            activity=activity,
            result="acquired",
        )
        return True
    before = _fetch_lock_row(database, project_id, rpc_priority=rpc_priority)
    extra: Optional[Dict[str, Any]] = None
    if before:
        extra = {
            "current_owner_type": before.get("owner_type"),
            "current_owner_id": before.get("owner_id"),
            "current_activity": before.get("activity"),
        }
    _log_coord(
        "try_acquire",
        project_id=project_id,
        owner_type=owner_type,
        owner_id=owner_id,
        activity=activity,
        result="busy",
        extra=extra,
    )
    return False


def heartbeat_project_activity(
    database: Any,
    project_id: str,
    owner_type: str,
    owner_id: str,
    activity: str,
    ttl_seconds: float,
    *,
    rpc_priority: int = 0,
) -> bool:
    _validate_project_id(project_id)
    _validate_owner_type(owner_type)
    _validate_owner_id(owner_id)
    _validate_activity(activity)
    _validate_ttl(ttl_seconds)
    now = time.time()
    lease_until = now + float(ttl_seconds)
    params = (activity, now, lease_until, project_id, owner_type, owner_id, now)
    res = _execute_coord(
        database,
        _HEARTBEAT_SQL,
        params,
        transaction_id=None,
        rpc_priority=rpc_priority,
    )
    ok = _affected(res) > 0
    _log_coord(
        "heartbeat",
        project_id=project_id,
        owner_type=owner_type,
        owner_id=owner_id,
        activity=activity,
        result="ok" if ok else "rejected",
    )
    return ok


def release_project_activity(
    database: Any,
    project_id: str,
    owner_type: str,
    owner_id: str,
    *,
    rpc_priority: int = 0,
) -> bool:
    _validate_project_id(project_id)
    _validate_owner_type(owner_type)
    _validate_owner_id(owner_id)
    row = _fetch_lock_row(database, project_id, rpc_priority=rpc_priority)
    res = _execute_coord(
        database,
        _RELEASE_SQL,
        (project_id, owner_type, owner_id),
        transaction_id=None,
        rpc_priority=rpc_priority,
    )
    ok = _affected(res) > 0
    act_log: str
    if row and row.get("activity") is not None:
        act_log = str(row["activity"])
    else:
        act_log = "(no_row)"
    _log_coord(
        "release",
        project_id=project_id,
        owner_type=owner_type,
        owner_id=owner_id,
        activity=act_log,
        result="ok" if ok else "rejected",
    )
    return ok


def get_project_activity(database: Any, project_id: str) -> Optional[Dict[str, Any]]:
    """Return the current lock row for ``project_id``, or None if no row exists."""
    _validate_project_id(project_id)
    return _fetch_lock_row(database, project_id)
