"""
Background session directory cleanup under TTL and liveness policy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Optional

from code_analysis.core.search_session.dead_detection import (
    DeadSessionVerdict,
    evaluate_session_liveness,
)
from code_analysis.core.search_session.directory import (
    BLOCKS_DIRNAME,
    BUFFER_DIRNAME,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    RELEVANCE_BLOCKS_DIRNAME,
    SERVICE_METADATA_FILENAME,
    SearchSessionDirectoryLayout,
)
from code_analysis.core.search_session.manifest import read_manifest
from code_analysis.core.search_session.policy import (
    SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX,
    SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN,
    SessionTTLPolicy,
    load_session_ttl_policy,
)
from code_analysis.core.search_session.service_metadata import read_service_metadata
from code_analysis.core.search_session.session import SearchSessionState
from code_analysis.core.search_timeouts import SEARCH_HARD_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset(
    {
        SearchSessionState.completed.value,
        SearchSessionState.failed.value,
        SearchSessionState.cancelled.value,
        SearchSessionState.timed_out.value,
        SearchSessionState.dead.value,
        SearchSessionState.expired.value,
        SearchSessionState.closed.value,
    }
)


def iter_session_directories(sessions_root: Path) -> Iterable[Path]:
    """Yield candidate session directories under ``sessions_root``."""
    if not sessions_root.is_dir():
        return
    for entry in sorted(sessions_root.iterdir()):
        if entry.is_dir():
            yield entry


def layout_from_directory(session_dir: Path) -> SearchSessionDirectoryLayout:
    """Build layout paths for an existing on-disk session directory."""
    return SearchSessionDirectoryLayout(
        root=session_dir,
        manifest_path=session_dir / MANIFEST_FILENAME,
        index_path=session_dir / INDEX_FILENAME,
        service_metadata_path=session_dir / SERVICE_METADATA_FILENAME,
        blocks_dir=session_dir / BLOCKS_DIRNAME,
        relevance_blocks_dir=session_dir / RELEVANCE_BLOCKS_DIRNAME,
        buffer_dir=session_dir / BUFFER_DIRNAME,
    )


def should_delete_session(
    layout: SearchSessionDirectoryLayout,
    *,
    policy: SessionTTLPolicy,
    now: float,
    hard_timeout_seconds: float = SEARCH_HARD_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Decide whether cleanup may remove one session directory.

    Expiry basis: idle time since ``last_access_at`` (service_metadata.json,
    refreshed on every ``search_get_page`` / ``search_get_status`` /
    ``search_close`` read -- see ``service_metadata.refresh_last_access``),
    NOT creation time. A paginated search session is designed to be read page
    by page over an unbounded stretch of wall-clock time -- a client may
    legitimately come back for page N several minutes after the initial
    ``search`` call -- so keying expiry off ``created_at`` would kill sessions
    still actively being paged through. Idle-since-last-access is the correct
    signal: it only starts the retention clock once nobody has touched the
    session for a while, regardless of how old the session itself is.
    """
    try:
        manifest = read_manifest(layout)
    except FileNotFoundError:
        return True, "missing_manifest"

    verdict = evaluate_session_liveness(
        manifest,
        hard_timeout_seconds=hard_timeout_seconds,
        now=now,
    )
    if verdict is DeadSessionVerdict.dead:
        return True, "dead"
    if verdict is DeadSessionVerdict.orphaned:
        return True, "orphaned"
    if verdict is DeadSessionVerdict.timed_out:
        return True, "timed_out"

    if manifest.status == SearchSessionState.running.value:
        return False, "live_running"

    try:
        metadata = read_service_metadata(layout)
        last_access_at = metadata.last_access_at
    except FileNotFoundError:
        last_access_at = manifest.last_access_at

    idle_seconds = now - last_access_at
    if manifest.status in _TERMINAL_STATUSES and idle_seconds > policy.ttl_seconds:
        return True, "ttl_expired"

    return False, "retained"


def cleanup_interval_seconds(policy: SessionTTLPolicy) -> float:
    """Effective periodic cleanup sweep interval, clamped to the safe bounds.

    ``policy.sweep_interval_seconds`` is the configured/default cadence
    (config: ``code_analysis.search_session.poll_interval``; constant
    default: ``DEFAULT_SEARCH_SESSION_SWEEP_INTERVAL_SECONDS``) -- an
    independent setting, not derived from ``ttl_seconds``. The clamp is a
    safety net for a misconfigured value that bypassed
    ``validate_session_ttl_policy`` (e.g. a config edited without running
    validation): too small would thrash the filesystem every tick, too large
    would silently defeat the "down to 1 minute" cadence requirement.
    """
    return max(
        float(SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN),
        min(
            float(SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX),
            float(policy.sweep_interval_seconds),
        ),
    )


async def _search_session_cleanup_loop(
    *,
    sessions_root: Path,
    config_path: Path,
    interval_seconds: float,
) -> None:
    """Return search session cleanup loop."""
    while True:
        try:
            # Offload the synchronous filesystem sweep (iterdir + rename +
            # rmtree) to a thread so this background loop never blocks the
            # main event loop.
            result = await asyncio.to_thread(
                sweep_expired_sessions,
                sessions_root=sessions_root,
                config_path=config_path,
                now=time.time(),
            )
            # Only log when something actually happened -- at a 1-minute
            # cadence, logging every empty tick would spam the log for no
            # operational value.
            if result.deleted:
                logger.info(
                    "Search session cleanup removed %d session(s), freed "
                    "%d bytes: %s",
                    len(result.deleted),
                    result.freed_bytes,
                    result.deleted,
                )
        except Exception:
            logger.exception("Search session cleanup failed")
        await asyncio.sleep(interval_seconds)


def register_search_session_cleanup(
    app: Any,
    *,
    sessions_root: Path,
    config_path: Path,
    app_config: dict[str, Any],
) -> None:
    """Register periodic background cleanup of expired search sessions."""
    policy = load_session_ttl_policy(app_config)
    interval_seconds = cleanup_interval_seconds(policy)

    @app.on_event("startup")
    async def _start_search_session_cleanup() -> None:
        """Return start search session cleanup."""
        asyncio.create_task(
            _search_session_cleanup_loop(
                sessions_root=sessions_root,
                config_path=config_path,
                interval_seconds=interval_seconds,
            )
        )


def _directory_size_bytes(root: Path) -> int:
    """Best-effort total size in bytes of every regular file under ``root``."""
    total = 0
    try:
        entries = list(root.rglob("*"))
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_file() and not entry.is_symlink():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _safe_remove_session_dir(session_dir: Path, *, sessions_root: Path) -> int:
    """Safely and atomically remove one session directory; return bytes freed.

    Safety, in order:

    1. Symlink refusal: ``session_dir`` itself must not be a symlink -- the
       sweeper never follows or deletes through a symlink entry under the
       sessions root.
    2. Containment: the resolved path must be a direct child of the resolved
       ``sessions_root``; anything else is refused and logged as an error
       rather than silently skipped, since it means ``iter_session_directories``
       (or a caller) handed this function a path it should never have produced.
    3. Atomicity: the directory is first renamed to a same-filesystem
       tombstone name inside ``sessions_root`` (a single atomic syscall), then
       the tombstone is ``rmtree``-d. A concurrent reader resolving the
       original path either observes the directory fully intact (its lookup
       raced ahead of the rename) or gets ENOENT (its lookup raced behind
       it) -- it can never observe a directory with only *some* of its files
       already removed. A reader that already holds an open file descriptor
       on a file inside the directory keeps working after the rename/rmtree
       (POSIX unlink-while-open semantics), so an in-flight read is never
       torn.
    4. Race tolerance: a ``FileNotFoundError`` from the rename (another sweep
       pass, or the explicit purge command, already removed it) is treated as
       "nothing to free", not an error.

    Args:
        session_dir: Session directory to remove (a direct child of
            ``sessions_root``, as yielded by ``iter_session_directories``).
        sessions_root: Configured sessions root.

    Returns:
        Freed size in bytes (measured before the rename), or 0 when refused
        or already gone.
    """
    if session_dir.is_symlink():
        logger.warning(
            "Search session cleanup refused to remove symlink entry: %s",
            session_dir,
        )
        return 0

    try:
        resolved_root = sessions_root.resolve()
        resolved_dir = session_dir.resolve()
    except OSError:
        return 0

    if resolved_dir.parent != resolved_root:
        logger.error(
            "Search session cleanup refused to remove path outside sessions "
            "root: %s (root=%s)",
            resolved_dir,
            resolved_root,
        )
        return 0

    size = _directory_size_bytes(resolved_dir)
    tombstone = resolved_root / f".purge-{resolved_dir.name}-{uuid.uuid4().hex}"
    try:
        os.rename(resolved_dir, tombstone)
    except FileNotFoundError:
        return 0
    shutil.rmtree(tombstone, ignore_errors=True)
    return size


@dataclass(frozen=True)
class SweepResult:
    """Outcome of one cleanup sweep pass.

    Attributes:
        deleted: Session ids (directory names) removed this pass.
        freed_bytes: Total bytes freed this pass (best-effort, measured
            before each removal).
    """

    deleted: list[str]
    freed_bytes: int


def sweep_expired_sessions(
    *,
    sessions_root: Path,
    config_path: Path,
    now: float,
    ttl_override_seconds: Optional[int] = None,
) -> SweepResult:
    """Remove session directories approved by cleanup policy.

    Args:
        sessions_root: Root directory holding one subdirectory per session.
        config_path: Server config path (retention/cadence policy source).
        now: Wall-clock time to evaluate idleness against.
        ttl_override_seconds: When given, replaces the configured/default
            retention (``policy.ttl_seconds``) for this sweep only -- used by
            the explicit ``search_sessions_purge`` command for an on-demand
            sweep. Never affects the periodic loop, which always calls this
            with ``ttl_override_seconds=None`` and therefore always uses the
            configured/default retention.

    Returns:
        ``SweepResult`` with the deleted session ids and bytes freed.
    """
    from code_analysis.core.storage_paths import load_raw_config

    config_data = load_raw_config(Path(config_path))
    policy = load_session_ttl_policy(config_data)
    if ttl_override_seconds is not None:
        policy = replace(policy, ttl_seconds=int(ttl_override_seconds))

    deleted: list[str] = []
    freed_bytes = 0
    for session_dir in iter_session_directories(sessions_root):
        layout = layout_from_directory(session_dir)
        delete, _reason = should_delete_session(layout, policy=policy, now=now)
        if not delete:
            continue
        freed = _safe_remove_session_dir(session_dir, sessions_root=sessions_root)
        deleted.append(session_dir.name)
        freed_bytes += freed
    return SweepResult(deleted=deleted, freed_bytes=freed_bytes)


def cleanup_expired_sessions(
    *,
    sessions_root: Path,
    config_path: Path,
    now: float,
) -> list[str]:
    """Remove session directories approved by cleanup policy; return deleted ids.

    Backward-compatible wrapper around ``sweep_expired_sessions`` (kept for
    existing callers/tests that only need the deleted-id list). Prefer
    ``sweep_expired_sessions`` directly for freed-byte accounting or the
    explicit-retention override.
    """
    return sweep_expired_sessions(
        sessions_root=sessions_root,
        config_path=config_path,
        now=now,
    ).deleted
