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
from typing import Any, Dict

from ..worker_status_file import (
    STATUS_OPERATION_IDLE,
    STATUS_OPERATION_POLLING,
    write_worker_status,
)
from .processing_cycle import run_one_cycle
from .processing_db_connect import ensure_database_connection

logger = logging.getLogger(__name__)


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
        logger.warning("SVO client manager not available, skipping vectorization")
        return {"processed": 0, "errors": 0}

    # Get socket path for database driver
    if not self.socket_path:
        from ..constants import DEFAULT_DB_DRIVER_SOCKET_DIR
        from pathlib import Path

        db_name = Path(self.db_path).stem
        socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
        socket_dir.mkdir(parents=True, exist_ok=True)
        socket_path = str(socket_dir / f"{db_name}_driver.sock")
    else:
        socket_path = self.socket_path
    logger.info(
        "[VECTORIZATION] Database socket_path=%s (db_path=%s)",
        socket_path,
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

    try:
        logger.info(
            "Starting universal vectorization worker, " "poll interval: %ss",
            poll_interval,
        )

        while not self._stop_event.is_set():
            (database, db_available, backoff, db_status_logged) = (
                await ensure_database_connection(
                    self,
                    socket_path,
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
            logger.info(
                "[CYCLE #%s] Loop iteration start (database available)",
                cycle_count,
            )
            write_worker_status(
                getattr(self, "status_file_path", None),
                STATUS_OPERATION_POLLING,
                current_file=None,
            )
            logger.info(
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
                logger.info(
                    "[CYCLE #%s] Complete in %.3fs: "
                    "(total: %s processed, %s errors)",
                    cycle_count,
                    cycle_duration,
                    total_processed,
                    total_errors,
                )
                logger.info(
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
                logger.info(
                    "[CYCLE #%s] No activity in %.3fs",
                    cycle_count,
                    cycle_duration,
                )

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
                        actual_poll_interval = int(backoff_delay)
                        logger.debug(
                            "Circuit breaker is OPEN, increasing poll interval "
                            "to %ss (backoff: %.1fs)",
                            actual_poll_interval,
                            backoff_delay,
                        )
            if cycle_activity:
                actual_poll_interval = min(actual_poll_interval, 2)

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
                logger.info(
                    "[CYCLE #%s] Sleeping %ss before next cycle",
                    cycle_count,
                    actual_poll_interval,
                )
                for _ in range(actual_poll_interval):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)

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
