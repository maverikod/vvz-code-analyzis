"""Unit tests for SearchSessionsPurgeCommand."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.search_sessions_purge_command import (
    SearchSessionsPurgeCommand,
)
from code_analysis.core.exceptions import ValidationError
from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    ServerProcessIdentity,
    capture_server_process_identity,
    write_manifest_atomic,
)
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


def _make_layout(sessions_root: Path, search_id: str):
    """Return a provisioned session directory layout."""
    return provision_search_session_directory(
        sessions_root=sessions_root, search_id=search_id
    )


def _write_manifest(
    layout,
    *,
    status: str,
    last_access_at: float,
    heartbeat_at: float,
    process: ServerProcessIdentity,
) -> None:
    """Write a manifest with an explicit process identity for liveness control."""
    manifest = SearchSessionManifest(
        search_id=layout.root.name,
        created_at=last_access_at,
        last_access_at=last_access_at,
        heartbeat_at=heartbeat_at,
        status=status,
        phase="indexed_search",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=process,
    )
    write_manifest_atomic(layout, manifest)


def _cmd(tmp_path: Path) -> SearchSessionsPurgeCommand:
    """Return a command instance wired to an isolated sessions_root/config_path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"code_analysis": {}}), encoding="utf-8")
    cmd = SearchSessionsPurgeCommand()
    cmd._get_search_sessions_root = MagicMock(
        return_value=tmp_path / "search_sessions"
    )
    cmd._resolve_config_path = MagicMock(return_value=config_path)
    return cmd


@pytest.mark.asyncio
async def test_purge_removes_idle_terminal_session_beyond_default_ttl(
    tmp_path: Path,
) -> None:
    """A closed session idle well past the default 1800s TTL is purged."""
    sessions_root = tmp_path / "search_sessions"
    layout = _make_layout(sessions_root, "idle-old-session")
    # capture_server_process_identity() ties the manifest to THIS test
    # process (genuinely alive with a matching start time), so liveness
    # classifies it as "live" rather than "dead"/"orphaned" -- isolating
    # this test to the idle-TTL decision, same rationale as
    # test_search_close_command.py's _write_manifest helper.
    _write_manifest(
        layout,
        status="closed",
        last_access_at=1.0,
        heartbeat_at=1.0,
        process=capture_server_process_identity(),
    )

    cmd = _cmd(tmp_path)
    result = await cmd.execute()

    assert isinstance(result, SuccessResult)
    assert result.data["purged_count"] == 1
    assert result.data["purged_session_ids"] == ["idle-old-session"]
    assert result.data["freed_bytes"] > 0
    assert not layout.root.exists()


@pytest.mark.asyncio
async def test_purge_retains_recently_closed_session_without_override(
    tmp_path: Path,
) -> None:
    """A just-closed session is retained when no max_age_seconds override is given."""
    import time

    sessions_root = tmp_path / "search_sessions"
    layout = _make_layout(sessions_root, "recent-session")
    now = time.time()
    _write_manifest(
        layout,
        status="closed",
        last_access_at=now,
        heartbeat_at=now,
        process=capture_server_process_identity(),
    )

    cmd = _cmd(tmp_path)
    result = await cmd.execute()

    assert isinstance(result, SuccessResult)
    assert result.data["purged_count"] == 0
    assert layout.root.exists()


@pytest.mark.asyncio
async def test_purge_max_age_seconds_zero_forces_immediate_sweep(
    tmp_path: Path,
) -> None:
    """max_age_seconds=0 sweeps an idle terminal session immediately, bypassing the default TTL."""
    import time

    sessions_root = tmp_path / "search_sessions"
    layout = _make_layout(sessions_root, "recent-session")
    now = time.time()
    _write_manifest(
        layout,
        status="closed",
        last_access_at=now,
        heartbeat_at=now,
        process=capture_server_process_identity(),
    )

    cmd = _cmd(tmp_path)
    result = await cmd.execute(max_age_seconds=0)

    assert isinstance(result, SuccessResult)
    assert result.data["purged_count"] == 1
    assert result.data["purged_session_ids"] == ["recent-session"]
    assert not layout.root.exists()


@pytest.mark.asyncio
async def test_purge_never_removes_live_running_session_even_with_zero_override(
    tmp_path: Path,
) -> None:
    """A live 'running' session survives max_age_seconds=0 -- safety over aggressiveness.

    ``heartbeat_at`` must be fresh (close to ``now``), not just the process
    identity -- a "running" session whose heartbeat has gone stale past
    ``SEARCH_HARD_TIMEOUT_SECONDS`` is legitimately classified "timed_out"
    (and correctly purged) by ``evaluate_session_liveness`` regardless of
    ``status``; this test isolates the "genuinely still active" case.
    """
    import time

    sessions_root = tmp_path / "search_sessions"
    layout = _make_layout(sessions_root, "running-session")
    now = time.time()
    _write_manifest(
        layout,
        status="running",
        last_access_at=now,
        heartbeat_at=now,
        process=capture_server_process_identity(),
    )

    cmd = _cmd(tmp_path)
    result = await cmd.execute(max_age_seconds=0)

    assert isinstance(result, SuccessResult)
    assert result.data["purged_count"] == 0
    assert layout.root.exists()


@pytest.mark.asyncio
async def test_purge_rejects_negative_max_age_seconds(tmp_path: Path) -> None:
    """A negative max_age_seconds is a validation error, not silently clamped."""
    cmd = _cmd(tmp_path)
    result = await cmd.execute(max_age_seconds=-1)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"  # type: ignore[comparison-overlap]


def test_validate_params_rejects_non_integer_max_age_seconds(tmp_path: Path) -> None:
    """Non-integer max_age_seconds raises ValidationError at validation time."""
    cmd = _cmd(tmp_path)
    with pytest.raises(ValidationError):
        cmd.validate_params({"max_age_seconds": "not-a-number"})


def test_schema_allows_null_max_age_seconds() -> None:
    """max_age_seconds is optional -- schema accepts integer or null."""
    schema = SearchSessionsPurgeCommand.get_schema()
    assert schema["properties"]["max_age_seconds"]["type"] == ["integer", "null"]
    assert "max_age_seconds" not in schema.get("required", [])
