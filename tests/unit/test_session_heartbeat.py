"""Unit tests for session heartbeat writer and stale detection."""

from __future__ import annotations

import json
from pathlib import Path

from code_analysis.core.search_session.directory import (
    BLOCKS_DIRNAME,
    BUFFER_DIRNAME,
    MANIFEST_FILENAME,
    RELEVANCE_BLOCKS_DIRNAME,
    SearchSessionDirectoryLayout,
)
from code_analysis.core.search_session.heartbeat import (
    is_heartbeat_stale,
    touch_heartbeat,
)
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    ServerProcessIdentity,
    write_manifest_atomic,
)


def _layout(tmp_path: Path) -> SearchSessionDirectoryLayout:
    """Return layout."""
    root = tmp_path / "session-1"
    root.mkdir()
    return SearchSessionDirectoryLayout(
        root=root,
        manifest_path=root / MANIFEST_FILENAME,
        index_path=root / "index.json",
        service_metadata_path=root / "service_metadata.json",
        blocks_dir=root / BLOCKS_DIRNAME,
        relevance_blocks_dir=root / RELEVANCE_BLOCKS_DIRNAME,
        buffer_dir=root / BUFFER_DIRNAME,
    )


def _write_manifest(
    layout: SearchSessionDirectoryLayout,
    *,
    heartbeat_at: float | None,
    status: str = "running",
) -> None:
    """Return write manifest."""
    manifest = SearchSessionManifest(
        search_id="session-1",
        created_at=100.0,
        last_access_at=100.0,
        heartbeat_at=heartbeat_at,
        status=status,
        phase="indexed_search",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=ServerProcessIdentity(main_pid=1, process_start_time=100.0),
    )
    write_manifest_atomic(layout, manifest)


def test_touch_heartbeat_updates_manifest(tmp_path: Path) -> None:
    """Verify test touch heartbeat updates manifest."""
    layout = _layout(tmp_path)
    _write_manifest(layout, heartbeat_at=50.0)

    touch_heartbeat(layout, now=200.0)

    with open(layout.manifest_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["heartbeat_at"] == 200.0


def test_is_heartbeat_stale_respects_hard_timeout() -> None:
    """Verify test is heartbeat stale respects hard timeout."""
    manifest = SearchSessionManifest(
        search_id="session-1",
        created_at=0.0,
        last_access_at=0.0,
        heartbeat_at=100.0,
        status="running",
        phase="indexed_search",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=ServerProcessIdentity(main_pid=1, process_start_time=0.0),
    )

    assert is_heartbeat_stale(
        manifest,
        hard_timeout_seconds=30.0,
        now=131.0,
    )
    assert not is_heartbeat_stale(
        manifest,
        hard_timeout_seconds=30.0,
        now=125.0,
    )
    assert not is_heartbeat_stale(
        manifest,
        hard_timeout_seconds=30.0,
        now=130.0,
    )


def test_is_heartbeat_stale_ignores_non_running() -> None:
    """Verify test is heartbeat stale ignores non running."""
    manifest = SearchSessionManifest(
        search_id="session-1",
        created_at=0.0,
        last_access_at=0.0,
        heartbeat_at=0.0,
        status="completed",
        phase="completion",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=ServerProcessIdentity(main_pid=1, process_start_time=0.0),
    )

    assert not is_heartbeat_stale(
        manifest,
        hard_timeout_seconds=10.0,
        now=1000.0,
    )
