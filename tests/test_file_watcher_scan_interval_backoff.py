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

import logging

from code_analysis.core.file_watcher_pkg.cycle_divergence import \
    log_cycle_divergence_if_any
from code_analysis.core.file_watcher_pkg.scan_interval_backoff import (
    _MAX_SCAN_INTERVAL, compute_real_work_from_cycle_stats,
    next_scan_interval)


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


def test_compute_real_work_from_cycle_stats_sums_queue_and_detected() -> None:
    """Both QUEUE-phase and SCAN-phase (detected) counters contribute."""
    cycle_stats = {
        "new_files": 1,
        "changed_files": 2,
        "deleted_files": 0,
        "detected_new_files": 3,
        "detected_changed_files": 0,
        "detected_deleted_files": 1,
    }
    assert compute_real_work_from_cycle_stats(cycle_stats) == 7


def test_compute_real_work_from_cycle_stats_missing_keys_default_zero() -> None:
    """A cycle_stats dict without the detected_* keys still works (defaults 0)."""
    assert compute_real_work_from_cycle_stats({"new_files": 2}) == 2
    assert compute_real_work_from_cycle_stats({}) == 0


def test_detected_only_cycle_resets_backoff_streak() -> None:
    """Bug 6d5ad353: scan detected changes (detected>0) but nothing was queued
    (new/changed/deleted=0) -- the combined real_work must still be > 0, so
    next_scan_interval resets the no-progress streak instead of growing it."""
    cycle_stats = {
        "new_files": 0,
        "changed_files": 0,
        "deleted_files": 0,
        "detected_new_files": 5,
        "detected_changed_files": 0,
        "detected_deleted_files": 0,
    }
    real_work = compute_real_work_from_cycle_stats(cycle_stats)
    assert real_work > 0
    interval, streak = next_scan_interval(
        scan_interval=60,
        real_work=real_work,
        consecutive_no_progress=9,
    )
    assert interval == 60
    assert streak == 0


def test_log_cycle_divergence_logs_when_totals_differ(caplog) -> None:
    """Detected != queued for a watch dir -> a single [CYCLE DIVERGENCE] line."""
    test_logger = logging.getLogger("test.cycle_divergence")
    with caplog.at_level(logging.WARNING, logger="test.cycle_divergence"):
        logged = log_cycle_divergence_if_any(
            "/watch/dir",
            5,
            0,
            0,
            0,
            0,
            0,
            logger_=test_logger,
        )
    assert logged is True
    assert any("[CYCLE DIVERGENCE]" in rec.message for rec in caplog.records)
    assert any("detected=5" in rec.message for rec in caplog.records)
    assert any("queued=0" in rec.message for rec in caplog.records)


def test_log_cycle_divergence_silent_when_totals_match(caplog) -> None:
    """Detected == queued -> no log line, returns False."""
    test_logger = logging.getLogger("test.cycle_divergence")
    with caplog.at_level(logging.WARNING, logger="test.cycle_divergence"):
        logged = log_cycle_divergence_if_any(
            "/watch/dir",
            2,
            1,
            0,
            2,
            1,
            0,
            logger_=test_logger,
        )
    assert logged is False
    assert not any("[CYCLE DIVERGENCE]" in rec.message for rec in caplog.records)


def test_log_cycle_divergence_silent_when_gap_is_all_expected_unsynced(caplog) -> None:
    """Bug DIVERGENCE netting: a chronic manifest-skip-only cycle must NOT warn.

    detected=3, queued=0, but all 3 are files build_project_disk_manifest skips
    every cycle for an already-understood reason (unsupported tree format /
    non-UTF-8 content). Netting expected_unsynced against the detected side
    must silence the warning; pre-fix (no netting) this cycle warned every
    single scan for a condition that will never resolve itself.
    """
    test_logger = logging.getLogger("test.cycle_divergence")
    with caplog.at_level(logging.WARNING, logger="test.cycle_divergence"):
        logged = log_cycle_divergence_if_any(
            "/watch/dir",
            3,
            0,
            0,
            0,
            0,
            0,
            expected_unsynced=3,
            logger_=test_logger,
        )
    assert logged is False
    assert not any("[CYCLE DIVERGENCE]" in rec.message for rec in caplog.records)


def test_log_cycle_divergence_still_fires_on_real_drop_with_expected_unsynced(
    caplog,
) -> None:
    """A genuine drop must still warn even when some skips are chronic/expected.

    detected=5 (3 chronic-expected + 2 unexplained), queued=0. Netting only
    removes the 3 expected ones, so 2 real, unexplained missing files must
    still trip the warning.
    """
    test_logger = logging.getLogger("test.cycle_divergence")
    with caplog.at_level(logging.WARNING, logger="test.cycle_divergence"):
        logged = log_cycle_divergence_if_any(
            "/watch/dir",
            5,
            0,
            0,
            0,
            0,
            0,
            expected_unsynced=3,
            logger_=test_logger,
        )
    assert logged is True
    assert any("[CYCLE DIVERGENCE]" in rec.message for rec in caplog.records)
    # Raw detected total is preserved in the log line even though netting
    # decided whether to warn -- operators must see the full accounting.
    assert any("detected=5" in rec.message for rec in caplog.records)
    assert any("expected_unsynced=3" in rec.message for rec in caplog.records)
