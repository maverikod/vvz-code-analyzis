"""
Database connection helper for vectorization worker.

Provides ensure_database_connection() with backoff and status-change-only
logging, used by the processing loop.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, TypeAlias

logger = logging.getLogger(__name__)

EnsureDatabaseConnectionResult: TypeAlias = tuple[Optional[Any], bool, float, bool]


async def ensure_database_connection(
    worker: Any,
    config_path: Path,
    db_available: bool = False,
    db_status_logged: bool = False,
    backoff: float = 1.0,
    backoff_max: float = 60.0,
) -> EnsureDatabaseConnectionResult:
    """
    Ensure a working database connection; test with list_projects().

    Logs "Database is now available" / "Database is now unavailable" only
    when the status changes. Caller should sleep(backoff) and use
    min(backoff*2, backoff_max) for next attempt on failure.

    Args:
        worker: Vectorization worker instance (for logging context; unused).
        config_path: Server ``config.json`` path; client is built via
            :func:`~code_analysis.core.database_client.factory.create_worker_database_client`.
        db_available: Previous availability state (for status-change logging).
        db_status_logged: Whether current unavailability was already logged.
        backoff: Current backoff seconds (returned on failure for sleep).
        backoff_max: Maximum backoff seconds.

    Returns:
        4-value tuple with fixed ordering:
        1) database: connected DB client instance or None on failure.
        2) db_available: current availability state after this check.
        3) backoff: delay value the caller should use before next retry.
        4) db_status_logged: whether unavailability status was logged in this
           state transition.

        Success path returns (database, True, 1.0, new_logged_flag).
        Failure path returns (None, False, backoff, logged_flag).
    """
    from ..database_client.factory import create_worker_database_client

    database: Optional[Any] = None
    try:
        logger.debug(
            "[VECTORIZATION] Creating database client (config_path=%s)",
            config_path,
        )
        database = create_worker_database_client(
            config_path=config_path,
        )
        database.connect()
        try:
            logger.debug("[VECTORIZATION] Testing connection with list_projects()")
            database.list_projects()
            if not db_available:
                logger.info("Database is now available")
            new_logged = True if not db_available else False
            return (database, True, 1.0, new_logged)
        except Exception as e:
            try:
                database.disconnect()
            except Exception:
                pass
            database = None
            if db_available:
                logger.warning("Database is now unavailable: %s", e)
                return (None, False, backoff, True)
            if not db_status_logged:
                logger.warning("Database is unavailable: %s", e)
                return (None, False, backoff, True)
            return (None, False, backoff, False)
    except Exception as e:
        if db_available:
            logger.warning("Database is now unavailable: %s", e)
            return (None, False, backoff, True)
        if not db_status_logged:
            logger.warning("Database is unavailable: %s", e)
            return (None, False, backoff, True)
        return (None, False, backoff, False)
