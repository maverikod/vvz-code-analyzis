"""
Processing loop for VectorizationWorker.

This module holds the outer cycle loop (interval between DB work checks) and
delegates batch processing to batch_processor. Chunker is called via WebSocket
only (no HTTP polling). Status "cycle_start" = starting a cycle (query DB for work).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from ..worker_status_file import (
    STATUS_OPERATION_IDLE,
    STATUS_OPERATION_POLLING,
    write_worker_status,
)
from .processing_cycle import run_one_cycle
from .processing_db_connect import ensure_database_connection

logger = logging.getLogger(__name__)

# Hard ceiling on poll interval: guards int()/range() from OverflowError when
# get_backoff_delay() returns infinity or a value too large for C ssize_t.
_MAX_POLL_INTERVAL = 3600


def _next_poll_interval(
    *,
    poll_interval: int,
    actual_poll_interval: int,
    committed_work: int,
    consecutive_no_progress: int,
    max_empty_iterations: int,
    empty_delay: float,
) -> Tuple[int, int]:
    """
    Decide the sleep interval for the next cycle and the updated no-progress streak.

    Fast-polls (capped at 2s) only while the cycle committed real work — rows
    actually vectorized/updated (``batch_processed`` + ``co_updated`` totals), not a
    bare activity flag and not a pending-count delta. When a cycle commits nothing,
    the no-progress streak grows; once the streak exceeds ``max_empty_iterations``,
    the sleep grows (doubling) starting from ``empty_delay``, never below the
    caller-supplied ``actual_poll_interval`` (which already reflects ``poll_interval``
    and any SVO circuit-breaker backoff), and capped at ``_MAX_POLL_INTERVAL``.

    Args:
        poll_interval: Configured base interval in seconds.
        actual_poll_interval: Interval computed so far this cycle (``poll_interval``,
            possibly raised by circuit-breaker backoff before this call).
        committed_work: Rows actually vectorized/updated this cycle. Zero means the
            cycle made no progress.
        consecutive_no_progress: Streak of prior consecutive no-progress cycles.
        max_empty_iterations: Streak length allowed before the sleep starts growing.
        empty_delay: Base delay in seconds the growth starts from.

    Returns:
        Tuple of (next_actual_poll_interval, next_consecutive_no_progress).
    """
    if committed_work > 0:
        return min(actual_poll_interval, 2), 0

    streak = consecutive_no_progress + 1
    if streak > max_empty_iterations:
        # Cap the doubling exponent: for any sane empty_delay, 2**39 already
        # dwarfs _MAX_POLL_INTERVAL, but an uncapped exponent (streak can grow
        # without bound while the worker idles) would eventually make the
        # int->float conversion below raise OverflowError.
        growth_cycles = min(streak - max_empty_iterations, 40)
        grown_delay = empty_delay * (2 ** (growth_cycles - 1))
        actual_poll_interval = min(
            max(actual_poll_interval, int(grown_delay)),
            _MAX_POLL_INTERVAL,
        )
    return actual_poll_interval, streak


async def process_chunks(self, poll_interval: int = 30) -> Dict[str, Any]:
    """
    Process non-vectorized chunks in continuous loop; cycle every poll_interval seconds.

    Universal worker that processes all projects from database.
    Worker works only with database - no filesystem access, no watch_dirs.
    Worker periodically queries database to discover projects with files/chunks needing vectorization.

    Runs indefinitely, checking for chunks to vectorize at specified intervals.
    Also requests chunking for files that need chunking.

    Handles database unavailability gracefully:
    - Checks database availability before each cycle
    - Logs status changes only (not on every cycle)
    - Continues working when database becomes available again

    Args:
        poll_interval: Interval in seconds between worker cycles (default: 30)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    if not self.svo_client_manager:
        logger.warning(
            "SVO client manager not configured: docstring chunking and FAISS maintenance "
            "still run; embedding RPC and batches that require SVO remain skipped until "
            "svo_config is present."
        )

    cfg_raw = getattr(self, "config_path", None)
    if not cfg_raw:
        logger.error(
            "VectorizationWorker requires config_path (server config.json) "
            "for the universal database driver."
        )
        return {"processed": 0, "errors": 0}
    cfg_path = Path(cfg_raw)
    try:
        from ..config import get_driver_config
        from ..storage_paths import load_raw_config

        drv = get_driver_config(load_raw_config(cfg_path)) or {}
        drv_type = drv.get("type", "unknown")
    except Exception:
        drv_type = "unknown"
    logger.info(
        "[VECTORIZATION] Database driver from config: type=%s (config_path=%s, db_path=%s)",
        drv_type,
        cfg_path,
        getattr(self, "db_path", None),
    )

    # Track database availability status
    db_available = False
    db_status_logged = False  # Track if we've logged the current status

    database: Any = None
    total_processed = 0
    total_errors = 0
    cycle_count = 0

    backoff = 1.0
    backoff_max = 60.0
    consecutive_no_progress = 0

    try:
        logger.info(
            "Starting universal vectorization worker, " "poll interval: %ss",
            poll_interval,
        )

        while not self._stop_event.is_set():
            # Reuse the existing client across cycles. Reconnecting every poll
            # (the previous behaviour) built a fresh PostgreSQL driver each cycle
            # — a main connection plus 5 pool connections — and overwrote the old
            # client without disconnecting it, orphaning 6 idle backend
            # connections per cycle until PostgreSQL ran out of slots. Only
            # (re)connect when there is no live client; the error path below sets
            # ``database = None`` (after disconnecting) to request a reconnect.
            if database is None:
                database, db_available, backoff, db_status_logged = (
                    await ensure_database_connection(
                        self,
                        cfg_path,
                        db_available=db_available,
                        db_status_logged=db_status_logged,
                        backoff=backoff,
                        backoff_max=backoff_max,
                    )
                )
                if database is None:
                    logger.debug(
                        "Retrying database connection in %.1fs...",
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, backoff_max)
                    continue

            cycle_count += 1
            logger.debug(
                "[CYCLE #%s] Loop iteration start (database available)",
                cycle_count,
            )
            write_worker_status(
                getattr(self, "status_file_path", None),
                STATUS_OPERATION_POLLING,
                current_file=None,
            )
            logger.debug(
                "[CYCLE #%s] Starting vectorization cycle",
                cycle_count,
            )

            cycle_start_time = time.time()
            delta_p = 0
            delta_e = 0
            cycle_activity = False
            cycle_step0_s = 0.0
            cycle_step1_query_s = 0.0
            cycle_step1_chunking_s = 0.0
            cycle_step2_s = 0.0
            cycle_step3_s = 0.0
            cycle_chunked_files = 0
            cycle_committed_work = 0
            try:
                (
                    delta_p,
                    delta_e,
                    cycle_activity,
                    cycle_step0_s,
                    cycle_step1_query_s,
                    cycle_step1_chunking_s,
                    cycle_step2_s,
                    cycle_step3_s,
                    cycle_chunked_files,
                    cycle_committed_work,
                ) = await run_one_cycle(
                    self,
                    database,
                    cycle_count,
                    total_processed,
                    total_errors,
                )
            except Exception as e:
                logger.error(
                    "Error in run_one_cycle: %s",
                    e,
                    exc_info=True,
                )
                error_str = str(e).lower()
                if (
                    "database" in error_str
                    or "db" in error_str
                    or "connection" in error_str
                ):
                    logger.warning(
                        "Database error detected, will reconnect on next cycle"
                    )
                    try:
                        database.disconnect()
                    except Exception:
                        pass
                    database = None
                    db_available = False
                    db_status_logged = False
                    backoff = 1.0
                    continue
                delta_p = 0
                delta_e = 0
                cycle_activity = False
                cycle_step0_s = 0.0
                cycle_step1_query_s = 0.0
                cycle_step1_chunking_s = 0.0
                cycle_step2_s = 0.0
                cycle_step3_s = 0.0
                cycle_chunked_files = 0
                cycle_committed_work = 0

            total_processed += delta_p
            total_errors += delta_e

            cycle_duration = time.time() - cycle_start_time
            write_worker_status(
                getattr(self, "status_file_path", None),
                "updating_stats",
                current_file=None,
                extra={"cycle": cycle_count},
            )
            if cycle_activity:
                logger.debug(
                    "[CYCLE #%s] Complete in %.3fs: "
                    "(total: %s processed, %s errors)",
                    cycle_count,
                    cycle_duration,
                    total_processed,
                    total_errors,
                )
                logger.debug(
                    "[CYCLE #%s] [TIMING] step0_reembed_s=%.2f step1_query_s=%.2f "
                    "step1_chunking_s=%.2f step2_assign_vector_id_s=%.2f "
                    "step3_rebuild_faiss_s=%.2f total_cycle_s=%.2f "
                    "chunks_processed=%s files_chunked=%s",
                    cycle_count,
                    cycle_step0_s,
                    cycle_step1_query_s,
                    cycle_step1_chunking_s,
                    cycle_step2_s,
                    cycle_step3_s,
                    cycle_duration,
                    total_processed,
                    cycle_chunked_files,
                )
            else:
                logger.debug(
                    "[CYCLE #%s] No activity in %.3fs",
                    cycle_count,
                    cycle_duration,
                )

            try:
                actual_poll_interval = poll_interval
                if self.svo_client_manager:
                    circuit_state = self.svo_client_manager.get_circuit_state()
                    state_str = (
                        getattr(circuit_state, "state", circuit_state)
                        if circuit_state is not None
                        else "closed"
                    )
                    if state_str == "open":
                        backoff_delay = self.svo_client_manager.get_backoff_delay()
                        if backoff_delay > poll_interval:
                            actual_poll_interval = int(
                                min(backoff_delay, _MAX_POLL_INTERVAL)
                            )
                            logger.debug(
                                "Circuit breaker is OPEN, increasing poll interval "
                                "to %ss (backoff: %.1fs)",
                                actual_poll_interval,
                                backoff_delay,
                            )
                actual_poll_interval, consecutive_no_progress = _next_poll_interval(
                    poll_interval=poll_interval,
                    actual_poll_interval=actual_poll_interval,
                    committed_work=cycle_committed_work,
                    consecutive_no_progress=consecutive_no_progress,
                    max_empty_iterations=self.max_empty_iterations,
                    empty_delay=self.empty_delay,
                )

                write_worker_status(
                    getattr(self, "status_file_path", None),
                    STATUS_OPERATION_IDLE,
                    current_file=None,
                    extra={
                        "phase": "sleeping",
                        "next_cycle_in_s": actual_poll_interval,
                    },
                )
                if not self._stop_event.is_set():
                    logger.debug(
                        "[CYCLE #%s] Sleeping %ss before next cycle",
                        cycle_count,
                        actual_poll_interval,
                    )
                    for _ in range(actual_poll_interval):
                        if self._stop_event.is_set():
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                logger.error(
                    "[CYCLE #%s] Error in poll-interval tail: %s — continuing to next cycle",
                    cycle_count,
                    e,
                    exc_info=True,
                )

    finally:
        if database is not None:
            try:
                database.disconnect()
            except Exception:
                pass

    logger.info(
        f"Vectorization worker stopped: {total_processed} total processed, "
        f"{total_errors} total errors over {cycle_count} cycles"
    )
    return {
        "processed": total_processed,
        "errors": total_errors,
        "cycles": cycle_count,
    }
