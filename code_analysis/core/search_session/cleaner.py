"""
Background session directory cleanup under TTL and liveness policy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

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
    resolve_search_sessions_root,
)
from code_analysis.core.search_session.manifest import read_manifest
from code_analysis.core.search_session.policy import (
    SessionTTLPolicy,
    load_session_ttl_policy,
)
from code_analysis.core.search_session.service_metadata import read_service_metadata
from code_analysis.core.search_session.session import SearchSessionState
from code_analysis.core.search_timeouts import SEARCH_HARD_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

_CLEANUP_INTERVAL_MIN_SECONDS = 60.0
_CLEANUP_INTERVAL_MAX_SECONDS = 300.0

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
    """Decide whether cleanup may remove one session directory."""
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
    """Derive periodic cleanup interval from configured session TTL."""
    quarter_ttl = float(policy.ttl_seconds) / 4.0
    return max(
        _CLEANUP_INTERVAL_MIN_SECONDS,
        min(_CLEANUP_INTERVAL_MAX_SECONDS, quarter_ttl),
    )


async def _search_session_cleanup_loop(
    *,
    config_dir: Path,
    interval_seconds: float,
) -> None:
    while True:
        try:
            deleted = cleanup_expired_sessions(config_dir=config_dir, now=time.time())
            if deleted:
                logger.info(
                    "Search session cleanup removed %d session(s): %s",
                    len(deleted),
                    deleted,
                )
        except Exception:
            logger.exception("Search session cleanup failed")
        await asyncio.sleep(interval_seconds)


def register_search_session_cleanup(
    app: Any,
    *,
    config_dir: Path,
    app_config: dict[str, Any],
) -> None:
    """Register periodic background cleanup of expired search sessions."""
    policy = load_session_ttl_policy(app_config)
    interval_seconds = cleanup_interval_seconds(policy)

    @app.on_event("startup")
    async def _start_search_session_cleanup() -> None:
        asyncio.create_task(
            _search_session_cleanup_loop(
                config_dir=config_dir,
                interval_seconds=interval_seconds,
            )
        )


def cleanup_expired_sessions(*, config_dir: Path, now: float) -> list[str]:
    """Remove session directories approved by cleanup policy."""
    config_path = config_dir / "config.json"
    with open(config_path, "r", encoding="utf-8") as handle:
        config_data = json.load(handle)
    policy = load_session_ttl_policy(config_data)

    sessions_root = resolve_search_sessions_root(config_dir)
    deleted: list[str] = []
    for session_dir in iter_session_directories(sessions_root):
        layout = layout_from_directory(session_dir)
        delete, _reason = should_delete_session(layout, policy=policy, now=now)
        if delete:
            shutil.rmtree(session_dir)
            deleted.append(session_dir.name)
    return deleted
