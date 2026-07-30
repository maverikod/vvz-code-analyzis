"""Unit tests for background session cleaner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.core.constants import (
    DEFAULT_SEARCH_SESSION_SWEEP_INTERVAL_SECONDS,
    DEFAULT_SEARCH_SESSION_TTL_SECONDS,
    SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX,
    SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN,
)
from code_analysis.core.search_session.cleaner import (
    _safe_remove_session_dir,
    cleanup_expired_sessions,
    cleanup_interval_seconds,
    layout_from_directory,
    should_delete_session,
    sweep_expired_sessions,
)
from code_analysis.core.search_session.dead_detection import DeadSessionVerdict
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    ServerProcessIdentity,
    write_manifest_atomic,
)
from code_analysis.core.search_session.policy import (
    SessionTTLPolicy,
    load_session_ttl_policy,
    validate_session_ttl_policy,
)
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
    """Return write session."""
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
    """Return config dir."""
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
    """Verify test expired idle session deleted."""
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
    """Verify test live running session with fresh heartbeat retained."""
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


# ---------------------------------------------------------------------------
# Retention/sweep-cadence constant + config-override duality
# (docs/... task requirement: both a constant default AND a config key).
# ---------------------------------------------------------------------------


def test_retention_and_sweep_defaults_come_from_constants_module() -> None:
    """Verify test retention and sweep defaults come from constants module."""
    policy = load_session_ttl_policy({})
    assert policy.ttl_seconds == DEFAULT_SEARCH_SESSION_TTL_SECONDS
    assert policy.sweep_interval_seconds == DEFAULT_SEARCH_SESSION_SWEEP_INTERVAL_SECONDS


def test_config_overrides_ttl_and_poll_interval_independently() -> None:
    """Verify test config overrides ttl and poll interval independently."""
    config_data = {
        "code_analysis": {
            "search_session": {
                "ttl_seconds": 42,
                "poll_interval": 77,
            }
        }
    }
    policy = load_session_ttl_policy(config_data)
    assert policy.ttl_seconds == 42
    assert policy.sweep_interval_seconds == 77
    # max_block_size_bytes was not overridden -> still the default.
    assert policy.max_block_size_bytes == 4_096


def test_validate_session_ttl_policy_rejects_out_of_range_poll_interval() -> None:
    """Verify test validate session ttl policy rejects out of range poll interval."""
    too_low = SessionTTLPolicy(
        ttl_seconds=1800,
        max_block_size_bytes=4096,
        sweep_interval_seconds=SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN - 1,
    )
    with pytest.raises(ValueError):
        validate_session_ttl_policy(too_low)

    too_high = SessionTTLPolicy(
        ttl_seconds=1800,
        max_block_size_bytes=4096,
        sweep_interval_seconds=SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX + 1,
    )
    with pytest.raises(ValueError):
        validate_session_ttl_policy(too_high)

    in_range = SessionTTLPolicy(
        ttl_seconds=1800, max_block_size_bytes=4096, sweep_interval_seconds=60
    )
    validate_session_ttl_policy(in_range)  # must not raise


def test_cleanup_interval_seconds_uses_configured_value_not_derived_from_ttl() -> (
    None
):
    """Verify test cleanup interval seconds uses configured value not derived from ttl."""
    policy = SessionTTLPolicy(
        ttl_seconds=999_999,  # deliberately huge -- old code derived interval = ttl/4
        max_block_size_bytes=4096,
        sweep_interval_seconds=90,
    )
    assert cleanup_interval_seconds(policy) == 90.0


def test_cleanup_interval_seconds_clamped_to_safe_bounds() -> None:
    """Verify test cleanup interval seconds clamped to safe bounds."""
    too_low = SessionTTLPolicy(
        ttl_seconds=1800, max_block_size_bytes=4096, sweep_interval_seconds=1
    )
    assert cleanup_interval_seconds(too_low) == float(
        SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN
    )

    too_high = SessionTTLPolicy(
        ttl_seconds=1800, max_block_size_bytes=4096, sweep_interval_seconds=999_999
    )
    assert cleanup_interval_seconds(too_high) == float(
        SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX
    )


# ---------------------------------------------------------------------------
# Expiry decision boundary (idle_seconds vs ttl_seconds).
# ---------------------------------------------------------------------------


def test_should_delete_session_boundary_exact_ttl_is_retained(
    config_dir: Path,
) -> None:
    """Idle time exactly equal to the TTL must NOT expire (strict '>' only).

    Liveness classification is patched to ``live`` so this test isolates the
    idle-vs-ttl boundary decision from dead/orphaned-process detection (the
    stub manifest's ``main_pid=1`` is not a real search-session process and
    would otherwise be classified ``orphaned`` regardless of TTL -- see
    ``test_live_running_session_with_fresh_heartbeat_retained`` for the same
    pattern).
    """
    sessions_root = config_dir / "data" / "search_sessions"
    session_dir = _write_session(
        sessions_root,
        "boundary-session",
        status="completed",
        heartbeat_at=100.0,
        last_access_at=100.0,
    )
    layout = layout_from_directory(session_dir)
    policy = SessionTTLPolicy(ttl_seconds=1800, max_block_size_bytes=1_048_576)

    with patch(
        "code_analysis.core.search_session.cleaner.evaluate_session_liveness",
        return_value=DeadSessionVerdict.live,
    ):
        delete, reason = should_delete_session(
            layout, policy=policy, now=100.0 + 1800.0
        )
    assert delete is False
    assert reason == "retained"


def test_should_delete_session_boundary_one_second_past_ttl_expires(
    config_dir: Path,
) -> None:
    """One second past the TTL boundary must expire (liveness patched to ``live``,
    see the exact-boundary test above for why)."""
    sessions_root = config_dir / "data" / "search_sessions"
    session_dir = _write_session(
        sessions_root,
        "boundary-session",
        status="completed",
        heartbeat_at=100.0,
        last_access_at=100.0,
    )
    layout = layout_from_directory(session_dir)
    policy = SessionTTLPolicy(ttl_seconds=1800, max_block_size_bytes=1_048_576)

    with patch(
        "code_analysis.core.search_session.cleaner.evaluate_session_liveness",
        return_value=DeadSessionVerdict.live,
    ):
        delete, reason = should_delete_session(
            layout, policy=policy, now=100.0 + 1800.0 + 1.0
        )
    assert delete is True
    assert reason == "ttl_expired"


# ---------------------------------------------------------------------------
# Deletion safety: path containment, symlink refusal, freed-byte accounting.
# ---------------------------------------------------------------------------


def test_safe_remove_refuses_path_outside_sessions_root(tmp_path: Path) -> None:
    """A directory that is not a direct child of sessions_root is never removed."""
    sessions_root = tmp_path / "search_sessions"
    sessions_root.mkdir()
    outside_dir = tmp_path / "not_a_session"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("do not delete me", encoding="utf-8")

    freed = _safe_remove_session_dir(outside_dir, sessions_root=sessions_root)

    assert freed == 0
    assert outside_dir.exists()
    assert (outside_dir / "secret.txt").exists()


def test_safe_remove_refuses_symlink_entry(tmp_path: Path) -> None:
    """A symlink under sessions_root is never followed/removed through."""
    sessions_root = tmp_path / "search_sessions"
    sessions_root.mkdir()
    real_target = tmp_path / "real_target"
    real_target.mkdir()
    (real_target / "keep.txt").write_text("keep me", encoding="utf-8")
    symlinked_session = sessions_root / "evil-symlink-session"
    os.symlink(real_target, symlinked_session, target_is_directory=True)

    freed = _safe_remove_session_dir(symlinked_session, sessions_root=sessions_root)

    assert freed == 0
    assert real_target.exists()
    assert (real_target / "keep.txt").exists()


def test_safe_remove_tolerates_already_gone_directory(tmp_path: Path) -> None:
    """A directory removed by a concurrent sweep is treated as freed=0, not an error."""
    sessions_root = tmp_path / "search_sessions"
    sessions_root.mkdir()
    session_dir = sessions_root / "already-gone"
    session_dir.mkdir()
    (session_dir / "f.txt").write_text("x", encoding="utf-8")
    # Simulate a race: another process already removed it by the time this
    # call runs (session_dir.resolve() is computed before the OS-level
    # rename, so removing it out from under this call still exercises the
    # FileNotFoundError branch inside _safe_remove_session_dir).
    import shutil as _shutil

    _shutil.rmtree(session_dir)

    freed = _safe_remove_session_dir(session_dir, sessions_root=sessions_root)
    assert freed == 0


def test_sweep_expired_sessions_reports_count_and_freed_bytes(
    config_dir: Path,
) -> None:
    """sweep_expired_sessions reports deleted ids and a positive freed_bytes total."""
    sessions_root = config_dir / "data" / "search_sessions"
    expired_dir = _write_session(
        sessions_root,
        "expired-session",
        status="completed",
        heartbeat_at=100.0,
        last_access_at=100.0,
    )
    (expired_dir / "extra_payload.json").write_text(
        "x" * 1000, encoding="utf-8"
    )
    retained_dir = _write_session(
        sessions_root,
        "fresh-session",
        status="completed",
        heartbeat_at=4999.0,
        last_access_at=4999.0,
    )

    with patch(
        "code_analysis.core.search_session.cleaner.evaluate_session_liveness",
        return_value=DeadSessionVerdict.live,
    ):
        result = sweep_expired_sessions(
            sessions_root=sessions_root,
            config_path=config_dir / "config.json",
            now=5000.0,
        )

    assert result.deleted == ["expired-session"]
    assert result.freed_bytes > 1000
    assert not expired_dir.exists()
    assert retained_dir.exists()


def test_sweep_expired_sessions_ttl_override_forces_immediate_sweep(
    config_dir: Path,
) -> None:
    """search_sessions_purge's max_age_seconds override sweeps sooner than the configured TTL."""
    sessions_root = config_dir / "data" / "search_sessions"
    # Closed 5 seconds ago -- far short of the configured 1800s TTL, so the
    # periodic sweep (no override) would retain it, but an explicit
    # max_age_seconds=0 override must sweep it immediately.
    session_dir = _write_session(
        sessions_root,
        "just-closed-session",
        status="closed",
        heartbeat_at=995.0,
        last_access_at=995.0,
    )

    with patch(
        "code_analysis.core.search_session.cleaner.evaluate_session_liveness",
        return_value=DeadSessionVerdict.live,
    ):
        not_yet = sweep_expired_sessions(
            sessions_root=sessions_root,
            config_path=config_dir / "config.json",
            now=1000.0,
        )
        assert not_yet.deleted == []
        assert session_dir.exists()

        overridden = sweep_expired_sessions(
            sessions_root=sessions_root,
            config_path=config_dir / "config.json",
            now=1000.0,
            ttl_override_seconds=0,
        )
    assert overridden.deleted == ["just-closed-session"]
    assert not session_dir.exists()


def test_sweep_expired_sessions_ttl_override_never_removes_running_session(
    config_dir: Path,
) -> None:
    """Even max_age_seconds=0 must never remove a live 'running' session."""
    sessions_root = config_dir / "data" / "search_sessions"
    session_dir = _write_session(
        sessions_root,
        "still-running-session",
        status="running",
        heartbeat_at=999.0,
        last_access_at=900.0,
    )

    with patch(
        "code_analysis.core.search_session.cleaner.evaluate_session_liveness",
        return_value=DeadSessionVerdict.live,
    ):
        result = sweep_expired_sessions(
            sessions_root=sessions_root,
            config_path=config_dir / "config.json",
            now=1000.0,
            ttl_override_seconds=0,
        )

    assert result.deleted == []
    assert session_dir.exists()
