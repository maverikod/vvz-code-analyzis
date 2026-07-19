"""
Unit tests for ``next_scan_interval`` progress-based backoff helper.

Verifies that real work (new/changed/deleted files) resets the scan interval
to the configured base and no-progress streak to 0, and that a sustained
no-progress streak grows the sleep interval (doubling from base), capped by
``_MAX_SCAN_INTERVAL``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.file_watcher_pkg.scan_interval_backoff import (
    _MAX_SCAN_INTERVAL, next_scan_interval)


def test_real_work_resets_interval_and_streak() -> None:
    """Real work resets the scan interval to base and streak to 0."""
    interval, streak = next_scan_interval(
        scan_interval=60,
        real_work=5,
        consecutive_no_progress=7,
    )
    assert interval == 60
    assert streak == 0


def test_real_work_resets_streak_even_with_zero_scan_interval() -> None:
    """Real work with scan_interval=0 returns 1 (clamped base) and streak 0."""
    interval, streak = next_scan_interval(
        scan_interval=0,
        real_work=1,
        consecutive_no_progress=3,
    )
    assert interval == 1
    assert streak == 0


def test_no_progress_grows_streak() -> None:
    """No real work grows the no-progress streak by 1 and doubles interval."""
    interval, streak = next_scan_interval(
        scan_interval=60,
        real_work=0,
        consecutive_no_progress=0,
    )
    # First no-progress cycle: streak becomes 1, interval doubles from base
    assert interval == 120  # base * 2^1
    assert streak == 1


def test_no_progress_grows_interval_monotonically() -> None:
    """Consecutive no-progress cycles grow the interval monotonically."""
    interval = 60
    streak = 0
    seen = []
    for _ in range(12):
        interval, streak = next_scan_interval(
            scan_interval=60,
            real_work=0,
            consecutive_no_progress=streak,
        )
        seen.append(interval)

    # Monotonic non-decrease.
    for prev, nxt in zip(seen, seen[1:]):
        assert nxt >= prev

    # Growth eventually exceeds base (60).
    assert max(seen) > 60


def test_zero_scan_interval_grows_from_clamped_base() -> None:
    """scan_interval=0 clamps to 1 before doubling on no-progress."""
    interval = None
    streak = 0
    for i in range(5):
        interval, streak = next_scan_interval(
            scan_interval=0,
            real_work=0,
            consecutive_no_progress=streak,
        )
    # After 5 cycles with no progress, interval should be > 1 (grown from clamped base).
    assert interval is not None
    assert interval > 1


def test_growth_capped_at_max_scan_interval() -> None:
    """Interval is capped at _MAX_SCAN_INTERVAL even with huge no-progress streak."""
    interval, streak = next_scan_interval(
        scan_interval=60,
        real_work=0,
        consecutive_no_progress=10_000,
    )
    assert interval <= _MAX_SCAN_INTERVAL
    assert streak == 10_001


def test_no_progress_sequence() -> None:
    """Sequence of no-progress cycles with scan_interval=60."""
    interval = 60
    streak = 0
    seen_intervals = []
    for _ in range(8):
        interval, streak = next_scan_interval(
            scan_interval=60,
            real_work=0,
            consecutive_no_progress=streak,
        )
        seen_intervals.append(interval)

    # First one should be 120 (base * 2^1, since streak becomes 1 on first no-progress).
    assert seen_intervals[0] == 120
    # Thereafter should grow monotonically.
    for prev, nxt in zip(seen_intervals, seen_intervals[1:]):
        assert nxt >= prev
