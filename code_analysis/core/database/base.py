"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base_chunks import (
    get_all_chunks_for_faiss_rebuild as _get_all_chunks_for_faiss_rebuild,
    get_non_vectorized_chunks as _get_non_vectorized_chunks,
    update_chunk_vector_id as _update_chunk_vector_id,
)
from .schema_creation import (
    run_create_schema,
    run_migrate_schema,
    run_migrate_to_uuid_projects,
)
from .schema_definition import (
    MIGRATION_METHODS,
    SCHEMA_VERSION,
    get_schema_definition,
)

from .code_chunk_sql import build_code_chunk_upsert_batch

logger = logging.getLogger(__name__)

# Passed to database_driver_pkg execute/execute_batch so run_* skips per-statement commit
# (same idea as SQLite named transactions); CodeDatabase then calls driver.commit().
LOCAL_DRIVER_TRANSACTION_ID = "local"


def create_driver_config_for_worker(
    db_path: Path, driver_type: str = "postgres", backup_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Create driver configuration for worker processes.

    SQLite support was removed; PostgreSQL is required. This helper only builds
    the ``{"path": ..., "backup_dir": ...}`` config shape historically used by
    file-based drivers — callers targeting PostgreSQL must supply full connection
    config (host/port/user/dbname) separately via
    :func:`~code_analysis.core.config.get_driver_config`.

    Args:
        db_path: Path to database file (used for ``backup_dir`` inference only).
        driver_type: Driver type (default: "postgres"); "sqlite"/"sqlite_proxy" is rejected.
        backup_dir: Optional backup directory path (if None, will be inferred from db_path in sync_schema)

    Returns:
        Driver configuration dict with 'type' and 'config' keys.

    Raises:
        ConfigurationError: If ``driver_type`` is "sqlite" or "sqlite_proxy".
    """
    if driver_type in ("sqlite", "sqlite_proxy"):
        from ..exceptions import ConfigurationError

        raise ConfigurationError(
            f"driver_type {driver_type!r} is not supported: SQLite support was "
            "removed; PostgreSQL is required. SQLite→PostgreSQL migrators were "
            "removed in the same release.",
            config_key="database.driver.type",
        )

    resolved_path = Path(db_path).resolve()

    config_dict: Dict[str, Any] = {
        "path": str(resolved_path),
    }

    # Add backup_dir if provided
    if backup_dir:
        config_dict["backup_dir"] = str(Path(backup_dir).resolve())

    return {
        "type": driver_type,
        "config": config_dict,
    }


# One lock per database (by driver instance or path)
# This allows concurrent access to different databases while serializing access to the same database
_db_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()  # Protects _db_locks dictionary


def _get_db_lock(lock_key: str) -> threading.Lock:
    """Get or create a lock for a specific database."""
    with _locks_lock:
        if lock_key not in _db_locks:
            _db_locks[lock_key] = threading.Lock()
        return _db_locks[lock_key]
