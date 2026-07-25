"""
Whole-project exclusive admin lock (no TTL/lease) — bugs 88f06abc, 5da73265.

Uses table ``project_exclusive_locks`` only. This is deliberately distinct from
``project_activity_locks`` (``core/worker_project_activity.py``): that table is a
short-lease watcher/indexer coordination lock with TTL/heartbeat; this module's
lock has no TTL and is held indefinitely until explicitly released by
``rename_project`` or ``emergency_unlock_project``. Callers must not embed raw
SQL for ``project_exclusive_locks``; use the public API below.

Driver-call convention matches ``worker_project_activity.py``: the ``database``
argument is the shared production driver object exposing ``.select()`` /
``.execute(sql, params, transaction_id=None)`` / ``.disconnect()`` — NOT the
``_execute``/``_fetchone`` migration-adapter shape used by
``core/database/migrations/*``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Final, Optional, Union, cast

logger = logging.getLogger(__name__)

_LOG_PREFIX: Final[str] = "[PROJECT_EXCLUSIVE_LOCK]"

TABLE: Final[str] = "project_exclusive_locks"

_ACQUIRE_SQL = (
    f"INSERT INTO {TABLE} (project_id, locked_at, owner, reason) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(project_id) DO NOTHING"
)

_RELEASE_SQL = f"DELETE FROM {TABLE} WHERE project_id = ?"


def _coerce_and_validate_project_id(project_id: Union[str, uuid.UUID]) -> str:
    """Coerce ``project_id`` to ``str`` (UUID-tolerant) and validate non-empty.

    This is the single coercion/validation choke point every public function
    in this module funnels ``project_id`` through (bug f96faa07). PostgreSQL
    drivers commonly hand back a raw ``uuid.UUID`` object for a ``UUID``
    column (e.g. rows from ``get_all_projects``); the previous
    str-only ``isinstance`` check rejected that object with ``ValueError``,
    which ``is_project_exclusively_locked`` then swallowed as a fail-open
    "not locked" result -- silently turning the whole-project lock gate into
    a no-op for every UUID-object caller. Accepting and normalizing
    ``uuid.UUID`` here closes that class of bug for every caller uniformly,
    including future ones, while still rejecting genuinely empty/blank/None
    input exactly as before.

    Args:
        project_id: Candidate project identifier: either a non-empty ``str``
            or a ``uuid.UUID`` instance.

    Returns:
        The canonical non-empty string form of ``project_id``.

    Raises:
        ValueError: If ``project_id`` is ``None``, empty, blank, or any type
            other than ``str``/``uuid.UUID``.
    """
    if isinstance(project_id, uuid.UUID):
        project_id = str(project_id)
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id must be a non-empty string")
    return project_id


def _validate_owner(owner: str) -> None:
    """Raise ``ValueError`` unless ``owner`` is a non-empty string.

    Args:
        owner: Candidate lock-owner identifier.

    Raises:
        ValueError: If ``owner`` is not a non-empty string.
    """
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner must be a non-empty string")


def _affected(result: Dict[str, Any]) -> int:
    """Return the non-negative ``affected_rows`` count from a driver result.

    Args:
        result: Return value of ``database.execute(...)``.

    Returns:
        ``affected_rows`` coerced to a non-negative int, or 0 when absent or
        not coercible.
    """
    n = result.get("affected_rows", 0)
    try:
        return int(n) if n is not None and int(n) >= 0 else 0
    except (TypeError, ValueError):
        return 0


def acquire_project_exclusive_lock(
    database: Any, project_id: Union[str, uuid.UUID], owner: str, reason: str
) -> bool:
    """Take the whole-project exclusive lock.

    Args:
        database: Shared driver object exposing ``.execute()``/``.select()``.
        project_id: Project UUID to lock; a ``str`` or a raw ``uuid.UUID``
            (e.g. straight from a PostgreSQL driver row) are both accepted
            and normalized to ``str`` before use.
        owner: Free-text identifier of the lock holder (e.g.
            ``"rename_project:<uuid>"``).
        reason: Free-text human-readable reason for the lock.

    Returns:
        True if the lock was newly acquired; False if it was already held by
        anyone (no TTL to steal — the caller must retry later or report busy).

    Raises:
        ValueError: If ``project_id`` is empty/None/blank (or any type other
            than ``str``/``uuid.UUID``), or ``owner`` is not a non-empty
            string.
    """
    project_id = _coerce_and_validate_project_id(project_id)
    _validate_owner(owner)
    now = time.time()
    res = cast(
        Dict[str, Any],
        database.execute(
            _ACQUIRE_SQL,
            (project_id, now, owner, reason),
            transaction_id=None,
        ),
    )
    ok = _affected(res) > 0
    logger.info(
        "%s op=acquire project_id=%r owner=%r reason=%r result=%s",
        _LOG_PREFIX,
        project_id,
        owner,
        reason,
        "acquired" if ok else "already_locked",
    )
    return ok


def release_project_exclusive_lock(
    database: Any, project_id: Union[str, uuid.UUID]
) -> None:
    """Unconditionally delete the lock row for ``project_id``.

    Args:
        database: Shared driver object exposing ``.execute()``.
        project_id: Project UUID to unlock; a ``str`` or a raw ``uuid.UUID``
            are both accepted and normalized to ``str`` before use.

    Returns:
        None. Idempotent no-op (no error) when nothing was locked.

    Raises:
        ValueError: If ``project_id`` is empty/None/blank (or any type other
            than ``str``/``uuid.UUID``).
    """
    project_id = _coerce_and_validate_project_id(project_id)
    res = cast(
        Dict[str, Any],
        database.execute(_RELEASE_SQL, (project_id,), transaction_id=None),
    )
    ok = _affected(res) > 0
    logger.info(
        "%s op=release project_id=%r result=%s",
        _LOG_PREFIX,
        project_id,
        "released" if ok else "noop_not_locked",
    )


def get_project_exclusive_lock(
    database: Any, project_id: Union[str, uuid.UUID]
) -> Optional[Dict[str, Any]]:
    """Return the lock row for ``project_id``, or None if unlocked.

    Args:
        database: Shared driver object exposing ``.select()``.
        project_id: Project UUID to look up; a ``str`` or a raw ``uuid.UUID``
            are both accepted and normalized to ``str`` before use.

    Returns:
        Dict with keys ``project_id``, ``locked_at``, ``owner``, ``reason``,
        or None if no lock row exists.

    Raises:
        ValueError: If ``project_id`` is empty/None/blank (or any type other
            than ``str``/``uuid.UUID``).
    """
    project_id = _coerce_and_validate_project_id(project_id)
    rows = database.select(TABLE, where={"project_id": project_id})
    if not rows:
        return None
    row = dict(rows[0])
    # Defensive shape guard: a genuine project_exclusive_locks row always carries
    # 'owner' and 'locked_at'. This also protects every caller against permissive
    # test doubles / driver stand-ins whose .select() ignores the table name and
    # returns an unrelated (e.g. 'projects') row for any call -- treat a row that
    # does not match this table's shape as "no lock" rather than a false positive,
    # consistent with this module's fail-open read-error philosophy.
    if "owner" not in row or "locked_at" not in row:
        return None
    return cast(Dict[str, Any], row)


def is_project_exclusively_locked(
    database: Any, project_id: Union[str, uuid.UUID]
) -> bool:
    """Return True iff a lock row exists for ``project_id``.

    Fail-open on lookup errors (returns False, logs a warning), matching the
    defensive style of ``try_acquire_project_activity``'s callers: a broken
    lookup must never permanently wedge unrelated project operations. A raw
    ``uuid.UUID`` object (e.g. straight from a PostgreSQL driver row) is
    accepted and normalized to ``str`` internally via
    ``_coerce_and_validate_project_id`` -- it is NOT a lookup error and must
    resolve the lock correctly, not fail open (bug f96faa07). Only a
    genuinely empty/None/blank ``project_id`` still fails open with the
    warning below.

    Args:
        database: Shared driver object exposing ``.select()``.
        project_id: Project UUID to check; a ``str`` or a raw ``uuid.UUID``
            are both accepted.

    Returns:
        True if a lock row exists; False if unlocked or the lookup failed.
    """
    try:
        return get_project_exclusive_lock(database, project_id) is not None
    except Exception as exc:
        logger.warning(
            "%s op=is_locked project_id=%r lookup_failed error=%s",
            _LOG_PREFIX,
            project_id,
            exc,
        )
        return False


def emergency_unlock_project_lock(
    database: Any,
    project_id: Union[str, uuid.UUID],
    *,
    force: bool,
    reason: str,
    mismatch: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Force-clear the lock, logging a structured audit line.

    This IS the audit entry for an emergency unlock — there is no separate
    audit table in this codebase; the structured log line plus the returned/
    reported record together serve that purpose.

    Args:
        database: Shared driver object exposing ``.select()``/``.execute()``.
        project_id: Project UUID to force-unlock; a ``str`` or a raw
            ``uuid.UUID`` are both accepted and normalized to ``str`` before
            use.
        force: Must be True to actually clear the lock; anything else raises.
        reason: Free-text human-readable reason for the forced clear, folded
            into the audit log line.
        mismatch: Optional caller-supplied disk/DB mismatch report to fold
            into the audit record (see ``emergency_unlock_project``'s own
            mismatch detection); passed through unchanged.

    Returns:
        Audit-record dict: ``{project_id, cleared, force, reason, mismatch,
        previous_lock, at}``. ``previous_lock`` is the lock row that existed
        before clearing, or None when nothing was actually locked (a valid
        "nothing to unlock" case, still logged).

    Raises:
        ValueError: If ``force`` is not True, or ``project_id`` is
            empty/None/blank (or any type other than ``str``/``uuid.UUID``).
    """
    project_id = _coerce_and_validate_project_id(project_id)
    if force is not True:
        raise ValueError(
            "emergency_unlock_project_lock refuses to clear without force=True"
        )
    previous_lock = get_project_exclusive_lock(database, project_id)
    release_project_exclusive_lock(database, project_id)
    at = time.time()
    logger.warning(
        "%s emergency_unlock project_id=%r force=%r reason=%r mismatch=%r "
        "previous_lock=%r",
        _LOG_PREFIX,
        project_id,
        force,
        reason,
        mismatch,
        previous_lock,
    )
    return {
        "project_id": project_id,
        "cleared": True,
        "force": force,
        "reason": reason,
        "mismatch": mismatch,
        "previous_lock": previous_lock,
        "at": at,
    }
