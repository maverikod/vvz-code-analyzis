"""
Unit tests for ``_next_poll_interval`` progress-based backoff helper.

Verifies that fast-polling (capped at 2s) only happens when a cycle commits
real work, and that a sustained no-progress streak grows the sleep interval
(doubling from ``empty_delay``, once past ``max_empty_iterations``), capped by
``_MAX_POLL_INTERVAL``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.vectorization_worker_pkg.processing import (
    _MAX_POLL_INTERVAL,
    _next_poll_interval,
)


def test_committed_work_fast_polls_and_resets_streak() -> None:
    """Committed work resets the no-progress streak and caps the poll at 2s."""
    actual, streak = _next_poll_interval(
        poll_interval=30,
        actual_poll_interval=30,
        committed_work=5,
        consecutive_no_progress=7,
        max_empty_iterations=3,
        empty_delay=5.0,
    )
    assert actual == 2
    assert streak == 0


def test_committed_work_fast_polls_even_with_small_actual_interval() -> None:
    """min(actual_poll_interval, 2) is honored even when actual is already below 2."""
    actual, streak = _next_poll_interval(
        poll_interval=30,
        actual_poll_interval=1,
        committed_work=1,
        consecutive_no_progress=0,
        max_empty_iterations=3,
        empty_delay=5.0,
    )
    assert actual == 1
    assert streak == 0


def test_no_progress_below_threshold_leaves_interval_unchanged() -> None:
    """Streak grows by 1 but interval is untouched while <= max_empty_iterations."""
    actual, streak = _next_poll_interval(
        poll_interval=30,
        actual_poll_interval=30,
        committed_work=0,
        consecutive_no_progress=0,
        max_empty_iterations=3,
        empty_delay=5.0,
    )
    assert actual == 30
    assert streak == 1

    actual2, streak2 = _next_poll_interval(
        poll_interval=30,
        actual_poll_interval=30,
        committed_work=0,
        consecutive_no_progress=streak,
        max_empty_iterations=3,
        empty_delay=5.0,
    )
    assert actual2 == 30
    assert streak2 == 2


def test_no_progress_past_threshold_grows_and_eventually_exceeds_base() -> None:
    """Driving consecutive no-progress cycles grows the sleep monotonically."""
    actual_poll_interval = 30
    consecutive_no_progress = 0
    seen = []
    for _ in range(15):
        actual_poll_interval, consecutive_no_progress = _next_poll_interval(
            poll_interval=30,
            actual_poll_interval=actual_poll_interval,
            committed_work=0,
            consecutive_no_progress=consecutive_no_progress,
            max_empty_iterations=3,
            empty_delay=5.0,
        )
        seen.append(actual_poll_interval)

    # Monotonic non-decrease once growth kicks in.
    for prev, nxt in zip(seen, seen[1:]):
        assert nxt >= prev

    assert max(seen) > 30


def test_no_progress_growth_capped_at_max_poll_interval() -> None:
    """Even a huge no-progress streak never exceeds _MAX_POLL_INTERVAL."""
    actual, streak = _next_poll_interval(
        poll_interval=30,
        actual_poll_interval=30,
        committed_work=0,
        consecutive_no_progress=10_000,
        max_empty_iterations=3,
        empty_delay=5.0,
    )
    assert actual <= _MAX_POLL_INTERVAL
    assert streak == 10_001
