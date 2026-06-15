"""Unit tests for background session cleaner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.core.search_session.cleaner import (
    cleanup_expired_sessions,
    layout_from_directory,
    should_delete_session,
)
from code_analysis.core.search_session.dead_detection import DeadSessionVerdict
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    ServerProcessIdentity,
    write_manifest_atomic,
)
from code_analysis.core.search_session.policy import SessionTTLPolicy
from code_analysis.core.search_session.service_metadata import (
    initialize_service_metadata,
)


def _write_session(
    sessions_root: Path,
    search_id: str,
    *,
    status: str,
    heartbeat_at: float,
    last_access_at: float,
) -> Path:
    session_dir = sessions_root / search_id
    session_dir.mkdir(parents=True)
    layout = layout_from_directory(session_dir)
    manifest = SearchSessionManifest(
        search_id=search_id,
        created_at=last_access_at,
        last_access_at=last_access_at,
        heartbeat_at=heartbeat_at,
        status=status,
        phase="indexed_search",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=ServerProcessIdentity(main_pid=1, process_start_time=last_access_at),
    )
    write_manifest_atomic(layout, manifest)
    initialize_service_metadata(layout, now=last_access_at)
    return session_dir


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    config = {
        "code_analysis": {
            "storage": {"db_path": str(tmp_path / "data" / "code_analysis.db")},
            "search_session": {
                "ttl_seconds": 1800,
                "max_block_size_bytes": 1_048_576,
            },
        }
    }
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


def test_expired_idle_session_deleted(config_dir: Path) -> None:
    sessions_root = config_dir / "data" / "search_sessions"
    session_dir = _write_session(
        sessions_root,
        "expired-session",
        status="completed",
        heartbeat_at=100.0,
        last_access_at=100.0,
    )

    deleted = cleanup_expired_sessions(
        sessions_root=sessions_root,
        config_path=config_dir / "config.json",
        now=5000.0,
    )

    assert deleted == ["expired-session"]
    assert not session_dir.exists()


def test_live_running_session_with_fresh_heartbeat_retained(config_dir: Path) -> None:
    sessions_root = config_dir / "data" / "search_sessions"
    session_dir = _write_session(
        sessions_root,
        "live-session",
        status="running",
        heartbeat_at=990.0,
        last_access_at=900.0,
    )
    layout = layout_from_directory(session_dir)
    policy = SessionTTLPolicy(ttl_seconds=1800, max_block_size_bytes=1_048_576)

    with patch(
        "code_analysis.core.search_session.cleaner.evaluate_session_liveness",
        return_value=DeadSessionVerdict.live,
    ):
        delete, reason = should_delete_session(
            layout,
            policy=policy,
            now=1000.0,
        )

        assert delete is False
        assert reason == "live_running"

        deleted = cleanup_expired_sessions(
            sessions_root=sessions_root,
            config_path=config_dir / "config.json",
            now=1000.0,
        )
        assert deleted == []
        assert session_dir.exists()
