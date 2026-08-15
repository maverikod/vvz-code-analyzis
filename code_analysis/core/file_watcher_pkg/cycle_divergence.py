"""
Per-watch-dir SCAN-vs-QUEUE divergence logging (bug 6d5ad353).

A scan cycle can detect on-disk changes (the ``[SCAN END]`` delta) that never
make it into the QUEUE-phase counters (``[QUEUE END]``) -- a skipped/locked
project, a bulk-sync short-circuit, a queue error, etc. Before this module,
that gap was invisible: only the QUEUE-phase totals fed the no-progress
backoff (:func:`code_analysis.core.file_watcher_pkg.scan_interval_backoff.
next_scan_interval`) and the cycle logs, so a project stuck dropping detected
changes every cycle silently kept growing the idle-backoff sleep instead of
surfacing the drop. This module names the discrepancy with a single grep-able
log line so it stops being silent.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def log_cycle_divergence_if_any(
    watch_dir: Union[Path, str],
    detected_new: int,
    detected_changed: int,
    detected_deleted: int,
    queued_new: int,
    queued_changed: int,
    queued_deleted: int,
    *,
    logger_: "logging.Logger | None" = None,
) -> bool:
    """
    Log ``[CYCLE DIVERGENCE]`` when SCAN-detected totals differ from QUEUE-phase
    totals for one watch directory this cycle.

    Args:
        watch_dir: Watch directory this cycle scanned (for the log line).
        detected_new/changed/deleted: ``[SCAN END]`` per-project delta totals
            summed across the watch dir.
        queued_new/changed/deleted: ``[QUEUE END]`` totals summed across the
            watch dir (what actually got queued for processing).
        logger_: Logger to use (defaults to this module's logger; tests pass
            their own to use ``caplog``).

    Returns:
        True when a divergence was logged, False when detected == queued.
    """
    log = logger_ if logger_ is not None else logger
    detected_total = int(detected_new) + int(detected_changed) + int(detected_deleted)
    queued_total = int(queued_new) + int(queued_changed) + int(queued_deleted)
    if detected_total == queued_total:
        return False
    log.warning(
        "[CYCLE DIVERGENCE] watch_dir=%s detected=%s queued=%s "
        "(detected_new=%s detected_changed=%s detected_deleted=%s "
        "queued_new=%s queued_changed=%s queued_deleted=%s)",
        watch_dir,
        detected_total,
        queued_total,
        detected_new,
        detected_changed,
        detected_deleted,
        queued_new,
        queued_changed,
        queued_deleted,
    )
    return True
