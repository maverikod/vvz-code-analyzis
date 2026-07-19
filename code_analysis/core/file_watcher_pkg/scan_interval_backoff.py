"""
Adaptive scan-interval backoff for MultiProjectFileWatcherWorker.

Mirrors ``vectorization_worker_pkg.processing._next_poll_interval``: a scan
cycle that found real on-disk changes (new/changed/deleted files across any
watched project) resets the sleep to ``scan_interval``; a cycle with no real
changes grows the sleep exponentially (doubling from ``scan_interval``),
capped at ``_MAX_SCAN_INTERVAL``, so a large idle watch surface does not keep
re-running full scan cycles back-to-back and pinning a core.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Tuple

# Hard ceiling on the scan sleep interval — mirrors
# vectorization_worker_pkg.processing._MAX_POLL_INTERVAL (guards int()/range()
# from unreasonable growth while idling).
_MAX_SCAN_INTERVAL = 3600


def next_scan_interval(
    *,
    scan_interval: int,
    real_work: int,
    consecutive_no_progress: int,
    max_scan_interval: int = _MAX_SCAN_INTERVAL,
) -> Tuple[int, int]:
    """
    Decide the sleep interval for the next scan cycle and the updated no-progress streak.

    The effective base interval is ``scan_interval`` clamped to at least 1 second
    (the config validator legally allows ``scan_interval = 0``, which must not
    turn into a busy loop). Any cycle with ``real_work > 0`` (new/changed/deleted
    files queued this cycle, across all watch dirs) resets the sleep to that base
    and the no-progress streak to 0. A cycle with no real work grows the streak by
    one and doubles the sleep from the base for each streak cycle, capped at
    ``max_scan_interval``.

    Args:
        scan_interval: Configured base interval in seconds (may be 0).
        real_work: Files queued/changed/removed this cycle, summed across all
            watch dirs (``cycle_stats`` new_files + changed_files + deleted_files).
        consecutive_no_progress: Streak of prior consecutive no-real-work cycles.
        max_scan_interval: Hard cap on the returned interval.

    Returns:
        Tuple of (next_effective_interval, next_consecutive_no_progress).
    """
    base = max(int(scan_interval), 1)
    if real_work > 0:
        return base, 0

    streak = consecutive_no_progress + 1
    # Cap the doubling exponent: for any sane base, 2**40 already dwarfs
    # max_scan_interval, but an uncapped exponent (streak can grow without bound
    # while idle) would eventually overflow int/float conversion.
    growth_cycles = min(streak, 40)
    grown = base * (2**growth_cycles)
    return min(grown, max_scan_interval), streak
