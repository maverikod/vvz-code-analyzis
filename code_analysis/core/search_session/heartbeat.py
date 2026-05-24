"""
Session heartbeat writer and stale detection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from code_analysis.core.search_session.directory import SearchSessionDirectoryLayout
from code_analysis.core.search_session.manifest import (
    SearchSessionManifest,
    update_manifest_atomic,
)

_RUNNING_STATUS = "running"


def make_heartbeat_hook(
    layout: SearchSessionDirectoryLayout,
) -> Callable[[], None]:
    """Return a no-arg callable for paginated search workers to refresh heartbeat."""

    def tick() -> None:
        touch_heartbeat(layout, now=time.time())

    return tick


def touch_heartbeat(layout: SearchSessionDirectoryLayout, *, now: float) -> None:
    """Atomically refresh ``heartbeat_at`` on the session manifest."""
    update_manifest_atomic(
        layout,
        lambda manifest: replace(manifest, heartbeat_at=now),
    )


def is_heartbeat_stale(
    manifest: SearchSessionManifest,
    *,
    hard_timeout_seconds: float,
    now: float,
) -> bool:
    """Return True when a running session heartbeat exceeds the hard timeout."""
    if manifest.status != _RUNNING_STATUS:
        return False
    heartbeat_at = manifest.heartbeat_at
    if heartbeat_at is None:
        return True
    elapsed = now - float(heartbeat_at)
    return cast(bool, elapsed > hard_timeout_seconds)
