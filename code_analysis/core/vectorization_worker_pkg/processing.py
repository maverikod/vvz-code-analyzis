"""
Processing loop for VectorizationWorker.

This module holds the outer polling loop and delegates heavy batch processing
to `batch_processor.process_embedding_ready_chunks` to keep file sizes small.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from .batch_processor import process_embedding_ready_chunks

logger = logging.getLogger(__name__)


async def process_chunks(self, poll_interval: int = 30) -> Dict[str, Any]:
    """
    Process non-vectorized chunks in continuous loop with polling interval.

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
        poll_interval: Interval in seconds between polling cycles (default: 30)

    Returns:
        Dictionary with processing statistics (only when stopped)
    """
    from ..database import CodeDatabase
    from ..faiss_manager import FaissIndexManager

    if not self.svo_client_manager:
        logger.warning("SVO client manager not available, skipping vectorization")
        return {"processed": 0, "errors": 0}

    from ..database import create_driver_config_for_worker

    driver_config = create_driver_config_for_worker(self.db_path)

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
            f"Starting universal vectorization worker, "
            f"poll interval: {poll_interval}s"
        )

        while not self._stop_event.is_set():
            cycle_count += 1
            cycle_start_time = time.time()

            # Check database availability
            if database is None or not db_available:
                try:
                    database = CodeDatabase(driver_config=driver_config)
                    # Test connection with a simple query
                    try:
                        database.get_all_projects()
                        # Connection successful
                        if not db_available:
                            # Status changed: unavailable -> available
                            logger.info("✅ Database is now available")
                            db_available = True
                            db_status_logged = True
                            backoff = 1.0  # Reset backoff
                        else:
                            db_status_logged = False  # Already logged as available
                    except Exception as e:
                        # Connection failed
                        if db_available:
                            # Status changed: available -> unavailable
                            logger.warning(f"⚠️  Database is now unavailable: {e}")
                            db_available = False
                            db_status_logged = True
                        elif not db_status_logged:
                            # First time logging unavailability
                            logger.warning(f"⚠️  Database is unavailable: {e}")
                            db_status_logged = True
                        else:
                            # Already logged, don't spam
                            db_status_logged = False

                        try:
                            database.close()
                        except Exception:
                            pass
                        database = None

                        # Wait with backoff before retrying
                        logger.debug(f"Retrying database connection in {backoff:.1f}s...")
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2.0, backoff_max)
                        continue
                except Exception as e:
                    # Failed to create database connection
                    if db_available:
                        # Status changed: available -> unavailable
                        logger.warning(f"⚠️  Database is now unavailable: {e}")
                        db_available = False
                        db_status_logged = True
                    elif not db_status_logged:
                        # First time logging unavailability
                        logger.warning(f"⚠️  Database is unavailable: {e}")
                        db_status_logged = True
                    else:
                        # Already logged, don't spam
                        db_status_logged = False

                    # Wait with backoff before retrying
                    logger.debug(f"Retrying database connection in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, backoff_max)
                    continue

            # Database is available, proceed with cycle
            logger.info(f"[CYCLE #{cycle_count}] Starting vectorization cycle")
            cycle_activity = False

            # Get projects with files/chunks needing vectorization (sorted by count, smallest first)
            try:
                projects = database.get_projects_with_vectorization_count()
                if not projects:
                    logger.info(f"[CYCLE #{cycle_count}] No projects with pending items found")
                else:
                    logger.info(
                        f"[CYCLE #{cycle_count}] Found {len(projects)} projects with pending items: "
                        f"{[(p['project_id'], p['pending_count']) for p in projects]}"
                    )
                    
                    # Process each project sequentially
                    for project in projects:
                        project_id = project["project_id"]
                        root_path = project["root_path"]
                        pending_count = project["pending_count"]
                        
                        logger.info(
                            f"Processing project {project_id} ({root_path}) with {pending_count} pending items"
                        )
                        
                        try:
                            # Create project-scoped FAISS manager
                            index_path = self.faiss_dir / f"{project_id}.bin"
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=self.vector_dim,
                            )
                            
                            # Step 1: Request chunking for files that need it
                            # Skip chunking requests if circuit breaker is open
                            if self.svo_client_manager:
                                circuit_state = self.svo_client_manager.get_circuit_state()
                                if circuit_state == "open":
                                    backoff_delay = self.svo_client_manager.get_backoff_delay()
                                    logger.debug(
                                        f"Skipping chunking requests for project {project_id} - "
                                        f"circuit breaker is OPEN (backoff: {backoff_delay:.1f}s)"
                                    )
                                else:
                                    try:
                                        files_to_chunk = database.get_files_needing_chunking(
                                            project_id=project_id,
                                            limit=5,  # Process 5 files per cycle
                                        )

                                        if files_to_chunk:
                                            logger.info(
                                                f"Found {len(files_to_chunk)} files needing chunking in project {project_id}, "
                                                "requesting chunking..."
                                            )
                                            chunked_count = await self._request_chunking_for_files(
                                                database, files_to_chunk
                                            )
                                            logger.info(
                                                f"Requested chunking for {chunked_count} files in project {project_id}"
                                            )
                                    except Exception as e:
                                        logger.error(
                                            f"Error requesting chunking for project {project_id}: {e}",
                                            exc_info=True,
                                        )
                            else:
                                # No SVO client manager, skip chunking
                                logger.debug(
                                    f"SVO client manager not available, skipping chunking requests for project {project_id}"
                                )

                            # Step 2: Assign vector_id in FAISS for chunks that already have embeddings.
                            # Temporarily set faiss_manager for batch processor
                            original_faiss_manager = getattr(self, "faiss_manager", None)
                            original_project_id = getattr(self, "project_id", None)
                            self.faiss_manager = faiss_manager
                            self.project_id = project_id
                            
                            try:
                                batch_processed, batch_errors = await process_embedding_ready_chunks(
                                    self, database
                                )
                                total_processed += batch_processed
                                total_errors += batch_errors
                                
                                if batch_processed > 0:
                                    cycle_activity = True
                            finally:
                                # Restore original values
                                self.faiss_manager = original_faiss_manager
                                self.project_id = original_project_id
                                
                        except Exception as e:
                            logger.error(
                                f"Error processing project {project_id}: {e}",
                                exc_info=True,
                            )
                            # Continue with next project
                        finally:
                            # Close FAISS manager for this project
                            try:
                                if faiss_manager:
                                    faiss_manager = None
                            except Exception:
                                pass
                    
                    # Step 3: Rebuild FAISS indexes for all projects at end of cycle
                    logger.info(f"[CYCLE #{cycle_count}] Rebuilding FAISS indexes for all projects...")
                    all_projects = database.get_all_projects()
                    for project in all_projects:
                        project_id = project["id"]
                        project_path = project.get("root_path", "unknown")
                        
                        try:
                            index_path = self.faiss_dir / f"{project_id}.bin"
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=self.vector_dim,
                            )
                            
                            logger.info(f"Rebuilding FAISS index for project {project_id} ({project_path})...")
                            vectors_count = await faiss_manager.rebuild_from_database(
                                database=database,
                                svo_client_manager=self.svo_client_manager,
                                project_id=project_id,
                            )
                            logger.info(
                                f"✅ FAISS index rebuilt for project {project_id}: {vectors_count} vectors"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to rebuild FAISS index for project {project_id}: {e}",
                                exc_info=True,
                            )
                            # Continue with next project
            except Exception as e:
                logger.error(f"Error processing projects: {e}", exc_info=True)
                # Check if error is due to database unavailability
                error_str = str(e).lower()
                if "database" in error_str or "db" in error_str or "connection" in error_str:
                    logger.warning("Database error detected, will reconnect on next cycle")
                    try:
                        database.close()
                    except Exception:
                        pass
                    database = None
                    db_available = False
                    db_status_logged = False
                    backoff = 1.0
                    continue
                batch_errors = 0
                batch_processed = 0

            cycle_duration = time.time() - cycle_start_time
            if cycle_activity:
                logger.info(
                    f"[CYCLE #{cycle_count}] Complete in {cycle_duration:.3f}s: "
                    f"(total: {total_processed} processed, {total_errors} errors)"
                )
                logger.debug(
                    f"[TIMING] [CYCLE #{cycle_count}] Total cycle time: {cycle_duration:.3f}s"
                )
            else:
                logger.info(
                    f"[CYCLE #{cycle_count}] No activity in {cycle_duration:.3f}s"
                )


            # Wait for next cycle (with early exit check)
            # Increase poll interval if services are unavailable (circuit breaker)
            actual_poll_interval = poll_interval
            if self.svo_client_manager:
                circuit_state = self.svo_client_manager.get_circuit_state()
                if circuit_state == "open":
                    backoff_delay = self.svo_client_manager.get_backoff_delay()
                    # Use backoff delay if it's longer than poll_interval
                    if backoff_delay > poll_interval:
                        actual_poll_interval = int(backoff_delay)
                        logger.debug(
                            f"Circuit breaker is OPEN, increasing poll interval "
                            f"to {actual_poll_interval}s (backoff: {backoff_delay:.1f}s)"
                        )

            if not self._stop_event.is_set():
                logger.debug(f"Waiting {actual_poll_interval}s before next cycle...")
                for _ in range(actual_poll_interval):
                    if self._stop_event.is_set():
                        break
                    await asyncio.sleep(1)

    finally:
        if database is not None:
            try:
                database.close()
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
