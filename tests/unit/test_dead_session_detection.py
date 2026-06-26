"""Unit tests for dead session detection."""

from __future__ import annotations

from unittest.mock import patch

from code_analysis.core.search_session.dead_detection import (
    DeadSessionVerdict,
    evaluate_session_liveness,
)
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    ServerProcessIdentity,
)


def _manifest(
    *, heartbeat_at: float | None, status: str = "running"
) -> SearchSessionManifest:
    """Return manifest."""
    return SearchSessionManifest(
        search_id="session-1",
        created_at=0.0,
        last_access_at=0.0,
        heartbeat_at=heartbeat_at,
        status=status,
        phase="indexed_search",
        request={},
        metrics=dict(DEFAULT_METRICS),
        process=ServerProcessIdentity(main_pid=4242, process_start_time=100.0),
    )


def test_missing_process_is_dead() -> None:
    """Verify test missing process is dead."""
    manifest = _manifest(heartbeat_at=100.0)

    with patch(
        "code_analysis.core.search_session.dead_detection._is_process_alive",
        return_value=False,
    ):
        verdict = evaluate_session_liveness(
            manifest,
            hard_timeout_seconds=30.0,
            now=200.0,
        )

    assert verdict is DeadSessionVerdict.dead


def test_stale_heartbeat_on_running_is_timed_out() -> None:
    """Verify test stale heartbeat on running is timed out."""
    manifest = _manifest(heartbeat_at=100.0)

    with (
        patch(
            "code_analysis.core.search_session.dead_detection._is_process_alive",
            return_value=True,
        ),
        patch(
            "code_analysis.core.search_session.dead_detection._probe_process_start_epoch",
            return_value=100.0,
        ),
    ):
        verdict = evaluate_session_liveness(
            manifest,
            hard_timeout_seconds=30.0,
            now=200.0,
        )

    assert verdict is DeadSessionVerdict.timed_out


def test_fresh_heartbeat_is_live() -> None:
    """Verify test fresh heartbeat is live."""
    manifest = _manifest(heartbeat_at=190.0)

    with (
        patch(
            "code_analysis.core.search_session.dead_detection._is_process_alive",
            return_value=True,
        ),
        patch(
            "code_analysis.core.search_session.dead_detection._probe_process_start_epoch",
            return_value=100.0,
        ),
    ):
        verdict = evaluate_session_liveness(
            manifest,
            hard_timeout_seconds=30.0,
            now=200.0,
        )

    assert verdict is DeadSessionVerdict.live
