"""
Release file locks held by client sessions that are no longer alive (TODO d75d5e9a).

A client session takes an exclusive lock on a file and is expected to release it.
When the client dies instead — an ai-editor container restart is the reported
case (ai-editor bug 3d1dd9ab, 2026-07-23) — nothing ever released the lock. The
session row survived the client, the lock survived the session, and every later
attempt to open that path from a new session failed until somebody ran
``session_delete`` by hand. Clients cannot fix this themselves: lock lifecycle is
entirely server-owned, and the conflict error did not even say who the holder was.

Liveness is already recorded: ``client_sessions.last_active_at`` is refreshed by
every session-scoped command (``touch_or_error``). What was missing is anything
that acts on it. This module supplies that:

* :func:`sweep_dead_sessions` — release everything a session that has been idle
  past the TTL still holds, reusing ``delete_client_session(force=True)`` so file
  locks, subordinate links, advisory leases and the on-disk ``.lock`` sidecars all
  go together. A session that comes back to a deleted id gets a clean
  SESSION_NOT_FOUND, which is an actionable error; a lock nobody can see or
  release is not.
* :func:`register_client_session_reaper` — run that sweep at startup, catching
  sessions orphaned by a server restart, and then periodically.
* :func:`describe_lock_holder` — the facts a conflict response should carry:
  who holds the lock, how long they have been idle, and whether they are already
  past the TTL and therefore about to be reaped.

The TTL is deliberately generous. A session that is idle is not necessarily dead
— a human may be staring at the file — so the default is an hour, and it is
configurable under ``code_analysis.client_session``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from code_analysis.core.constants import (
    CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MAX,
    CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MIN,
    CLIENT_SESSION_TTL_SECONDS_MAX,
    CLIENT_SESSION_TTL_SECONDS_MIN,
    DEFAULT_CLIENT_SESSION_SWEEP_INTERVAL_SECONDS,
    DEFAULT_CLIENT_SESSION_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

CONFIG_SECTION = "client_session"
CONFIG_KEY_TTL = "ttl_seconds"
CONFIG_KEY_SWEEP_INTERVAL = "poll_interval"
CONFIG_KEY_ENABLED = "reap_dead_sessions"

#: Seconds per Julian day — ``last_active_at`` is stored as a Julian day REAL on
#: both drivers (the Postgres driver rewrites ``julianday('now')`` to
#: ``EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)``), so idle time is a subtraction
#: scaled by this.
SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class SessionReaperPolicy:
    """
    Validated liveness policy for client sessions.

    Attributes:
        ttl_seconds: Idle time after which a session is considered dead and
            everything it holds is released. Config:
            ``code_analysis.client_session.ttl_seconds``.
        sweep_interval_seconds: Cadence of the background sweep. Config:
            ``code_analysis.client_session.poll_interval``.
        enabled: Whether the background sweep runs at all. Config:
            ``code_analysis.client_session.reap_dead_sessions``. The manual
            ``session_reap_dead`` command works regardless.
    """

    ttl_seconds: int
    sweep_interval_seconds: int
    enabled: bool = True


@dataclass(frozen=True)
class ReapedSession:
    """One session released by a sweep, and what it was holding."""

    session_id: str
    idle_seconds: float
    released_lock_count: int
    released_subordinate_count: int
    released_advisory_lease_count: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view for command responses."""
        return {
            "session_id": self.session_id,
            "idle_seconds": round(self.idle_seconds, 3),
            "released_lock_count": self.released_lock_count,
            "released_subordinate_count": self.released_subordinate_count,
            "released_advisory_lease_count": self.released_advisory_lease_count,
        }


@dataclass(frozen=True)
class ReapResult:
    """Outcome of one sweep."""

    reaped: tuple[ReapedSession, ...]
    failed: tuple[tuple[str, str], ...]
    ttl_seconds: int

    @property
    def released_lock_total(self) -> int:
        """Total file locks released across every reaped session."""
        return sum(item.released_lock_count for item in self.reaped)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view for command responses."""
        return {
            "ttl_seconds": self.ttl_seconds,
            "reaped_session_count": len(self.reaped),
            "released_lock_total": self.released_lock_total,
            "reaped": [item.as_dict() for item in self.reaped],
            "failed": [{"session_id": sid, "error": err} for sid, err in self.failed],
        }


def _clamp(value: int, *, minimum: int, maximum: int) -> int:
    """Constrain ``value`` to the inclusive range."""
    return max(minimum, min(maximum, value))


def load_session_reaper_policy(
    config_data: Optional[Mapping[str, Any]],
) -> SessionReaperPolicy:
    """
    Load the client-session liveness policy from configuration.

    Out-of-range and unparsable values are clamped rather than rejected: this
    policy governs a background janitor, and a misconfigured number must not
    keep the server from starting or silently disable lock recovery.

    Args:
        config_data: Raw config dict, or None.

    Returns:
        A validated, clamped policy.
    """
    section: Mapping[str, Any] = {}
    if isinstance(config_data, Mapping):
        code_analysis = config_data.get("code_analysis")
        if isinstance(code_analysis, Mapping):
            candidate = code_analysis.get(CONFIG_SECTION)
            if isinstance(candidate, Mapping):
                section = candidate

    ttl = _coerce_int(section.get(CONFIG_KEY_TTL), DEFAULT_CLIENT_SESSION_TTL_SECONDS)
    sweep = _coerce_int(
        section.get(CONFIG_KEY_SWEEP_INTERVAL),
        DEFAULT_CLIENT_SESSION_SWEEP_INTERVAL_SECONDS,
    )
    enabled_raw = section.get(CONFIG_KEY_ENABLED, True)
    return SessionReaperPolicy(
        ttl_seconds=_clamp(
            ttl,
            minimum=CLIENT_SESSION_TTL_SECONDS_MIN,
            maximum=CLIENT_SESSION_TTL_SECONDS_MAX,
        ),
        sweep_interval_seconds=_clamp(
            sweep,
            minimum=CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MIN,
            maximum=CLIENT_SESSION_SWEEP_INTERVAL_SECONDS_MAX,
        ),
        enabled=bool(enabled_raw),
    )


def _coerce_int(value: Any, fallback: int) -> int:
    """Return ``value`` as an int, falling back on anything unusable."""
    if isinstance(value, bool) or value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _idle_seconds(row: Mapping[str, Any], now_julian: Optional[float]) -> float:
    """Seconds since ``last_active_at``, or 0.0 when it cannot be computed."""
    if now_julian is None:
        return 0.0
    try:
        last_active = float(row.get("last_active_at"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (now_julian - last_active) * SECONDS_PER_DAY)


def _now_julian(database: Any) -> Optional[float]:
    """Read the database's current time as a Julian day, or None on failure."""
    try:
        res = database.execute("SELECT julianday('now') AS now_julian")
    except Exception:
        return None
    rows = res.get("data") if isinstance(res, dict) else None
    if not rows:
        return None
    try:
        return float(rows[0]["now_julian"])
    except (KeyError, TypeError, ValueError):
        return None


def sweep_dead_sessions(
    database: Any,
    *,
    ttl_seconds: int,
    only_session_ids: Optional[Sequence[str]] = None,
) -> ReapResult:
    """
    Release everything held by sessions idle for longer than ``ttl_seconds``.

    Each session is reaped independently: one row that fails to release does not
    abort the sweep, because the whole point is to unstick the others.

    Args:
        database: DatabaseClient instance.
        ttl_seconds: Idle threshold in seconds; must be positive.
        only_session_ids: When given, restrict the sweep to these sessions.
            The idle test still applies to each of them -- naming a session
            asks for it to be reaped IF it is dead, it does not force the
            release of a live one.

    Returns:
        A :class:`ReapResult` naming every session reaped and every failure.

    Raises:
        ValueError: When ``ttl_seconds`` is not positive.
    """
    if ttl_seconds <= 0:
        raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")

    from code_analysis.core.client_sessions import (
        delete_client_session,
        list_client_sessions,
    )

    stale_rows: Sequence[Mapping[str, Any]] = list_client_sessions(
        database, stale_threshold_seconds=ttl_seconds
    )
    scope = (
        {str(sid).strip() for sid in only_session_ids if str(sid).strip()}
        if only_session_ids is not None
        else None
    )
    now_julian = _now_julian(database)

    reaped: list[ReapedSession] = []
    failed: list[tuple[str, str]] = []
    for row in stale_rows:
        session_id = str(row.get("session_id") or "").strip()
        if not session_id:
            continue
        if scope is not None and session_id not in scope:
            continue
        try:
            outcome = delete_client_session(database, session_id, force=True)
        except Exception as exc:  # one bad session must not stop the sweep
            failed.append((session_id, f"{type(exc).__name__}: {exc}"))
            logger.warning("Could not reap dead session %s: %s", session_id, exc)
            continue
        reaped.append(
            ReapedSession(
                session_id=session_id,
                idle_seconds=_idle_seconds(row, now_julian),
                released_lock_count=int(outcome.get("released_lock_count") or 0),
                released_subordinate_count=int(
                    outcome.get("released_subordinate_count") or 0
                ),
                released_advisory_lease_count=int(
                    outcome.get("released_advisory_lease_count") or 0
                ),
            )
        )
    return ReapResult(
        reaped=tuple(reaped), failed=tuple(failed), ttl_seconds=ttl_seconds
    )


def describe_lock_holder(
    database: Any,
    holder_session_id: str,
    *,
    ttl_seconds: int,
) -> dict[str, Any]:
    """
    Describe the session holding a lock, for an actionable conflict response.

    A bare "file is locked" leaves a client with nowhere to go. Naming the
    holder and its idle time lets the client say whether it is waiting on a live
    peer or on a corpse that the reaper is about to clear.

    Args:
        database: DatabaseClient instance.
        holder_session_id: Session id currently holding the lock.
        ttl_seconds: The active TTL, echoed so the client can interpret idleness.

    Returns:
        Dict with holder_session_id, holder_exists, holder_idle_seconds,
        holder_expired and ttl_seconds. Never raises: a conflict response must
        not fail because the diagnostic lookup did.
    """
    details: dict[str, Any] = {
        "holder_session_id": holder_session_id,
        "holder_exists": False,
        "holder_idle_seconds": None,
        "holder_expired": False,
        "ttl_seconds": ttl_seconds,
    }
    try:
        from code_analysis.core.client_sessions import get_client_session

        row = get_client_session(database, holder_session_id)
        if row is None:
            return details
        details["holder_exists"] = True
        details["holder_comment"] = row.get("comment")
        idle = _idle_seconds(row, _now_julian(database))
        details["holder_idle_seconds"] = round(idle, 3)
        details["holder_expired"] = idle > ttl_seconds
    except Exception as exc:  # diagnostics must never break the real answer
        logger.debug("Could not describe lock holder %s: %s", holder_session_id, exc)
    return details


async def _reaper_loop(
    *,
    database_factory: Any,
    policy: SessionReaperPolicy,
) -> None:
    """Run the sweep immediately, then on the configured cadence, forever."""
    while True:
        try:
            database = database_factory()
            result = await asyncio.to_thread(
                sweep_dead_sessions, database, ttl_seconds=policy.ttl_seconds
            )
            # Silence on an empty tick: at this cadence, logging "nothing to do"
            # would bury the one line that matters.
            if result.reaped:
                logger.info(
                    "Reaped %d dead client session(s) idle past %ds, releasing "
                    "%d file lock(s): %s",
                    len(result.reaped),
                    policy.ttl_seconds,
                    result.released_lock_total,
                    [item.session_id for item in result.reaped],
                )
            if result.failed:
                logger.warning(
                    "Could not reap %d dead session(s): %s",
                    len(result.failed),
                    result.failed,
                )
        except Exception:
            logger.exception("Client session reaper sweep failed")
        await asyncio.sleep(policy.sweep_interval_seconds)


def register_client_session_reaper(
    app: Any,
    *,
    database_factory: Any,
    app_config: Optional[Mapping[str, Any]] = None,
) -> SessionReaperPolicy:
    """
    Register the background sweep that releases locks held by dead sessions.

    The first sweep runs as soon as the app starts, which is what recovers locks
    orphaned by a server restart — the reported failure mode.

    Args:
        app: FastAPI application to hook the startup event on.
        database_factory: Zero-argument callable returning a DatabaseClient.
            A factory rather than a client so the loop never holds a connection
            across its idle period.
        app_config: Raw config dict used to load the policy.

    Returns:
        The policy in force, so callers can log or assert on it.
    """
    policy = load_session_reaper_policy(app_config)
    if not policy.enabled:
        logger.info("Client session reaper disabled by configuration")
        return policy

    @app.on_event("startup")
    async def _start_client_session_reaper() -> None:
        """Start the reaper loop as a background task."""
        asyncio.create_task(
            _reaper_loop(database_factory=database_factory, policy=policy)
        )

    return policy
