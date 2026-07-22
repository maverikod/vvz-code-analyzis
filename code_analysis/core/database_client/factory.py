"""
Factory for the PostgreSQL driver from server config (PostgreSQL in-process only).

SQLite support was removed; PostgreSQL is the only supported driver, always
in-process (no Unix socket, no database driver subprocess).

Stage 2 (layer collapse, THE FLIP): construction now hands out a connected
:class:`~code_analysis.core.database_driver_pkg.drivers.postgres.PostgreSQLDriver`
directly instead of wrapping it in ``RPCHandlers`` + ``InProcessRpcClient`` +
:class:`DatabaseClient` -- every caller only ever used the driver-compatible
primitive surface (``execute``/``select``/``insert``/... plus the driver-direct
free functions ported in earlier stage-2 commits), which the driver already
implements natively; the ``DatabaseClient`` hop was a same-process detour, never
a real RPC boundary (there is no Unix socket for PostgreSQL). Callers must not
call ``.connect()`` on the returned object again -- the driver returned here is
already connected (``.connect(config)`` already ran inside this factory).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from code_analysis.core.config import get_driver_config
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.exceptions import ConfigurationError
from code_analysis.core.storage_paths import (
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)

logger = logging.getLogger(__name__)


def resolve_driver_config_like_main_workers(
    config_data: Dict[str, Any], config_path: Path
) -> Dict[str, Any]:
    """Align driver config with :func:`code_analysis.main_workers.startup_database_driver`."""
    driver_config = get_driver_config(config_data)
    if not driver_config or not driver_config.get("type"):
        raise ValueError("Missing code_analysis.database.driver configuration")
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    ensure_storage_dirs(storage)
    config_dict: Dict[str, Any] = dict(driver_config.get("config") or {})
    driver_type = driver_config.get("type")
    if driver_type != "postgres":
        raise ConfigurationError(
            f"driver_type {driver_type!r} is not supported: SQLite support was "
            "removed; PostgreSQL is required.",
            config_key="database.driver.type",
        )
    resolved = {"type": driver_type, "config": config_dict}
    if "query_log_path" not in config_dict:
        config_dict["query_log_path"] = str(storage.log_dir / "database_queries.jsonl")
    return resolved


def create_database_client_from_config_path(
    config_path: Path,
    *,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delay: float = 0.1,
    pool_size: int = 5,
) -> PostgreSQLDriver:
    """Build and connect a :class:`PostgreSQLDriver` for the configured driver.

    ``timeout``/``max_retries``/``retry_delay``/``pool_size`` are accepted for
    call-site compatibility with the pre-flip signature; the driver manages its
    own connection pool and retry policy from ``config`` (see
    :meth:`PostgreSQLDriver.connect`), so they are otherwise unused here.

    Returns:
        An already-connected :class:`PostgreSQLDriver`. Do not call ``.connect()``
        on it again.
    """
    _ = (timeout, max_retries, retry_delay, pool_size)
    config_data = load_raw_config(config_path)
    resolved = resolve_driver_config_like_main_workers(config_data, config_path)

    driver = PostgreSQLDriver()
    driver.connect(resolved["config"])
    return driver


def create_worker_database_client(
    *,
    config_path: Path,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delay: float = 0.1,
    pool_size: int = 5,
) -> PostgreSQLDriver:
    """Build and connect a :class:`PostgreSQLDriver` from server config only (same as the main process).

    Workers must use this entry point so the database backend is chosen solely from
    ``code_analysis.database.driver`` in ``config_path`` (PostgreSQL in-process).
    Do not construct :class:`DatabaseClient` with a raw ``socket_path`` in worker code.

    Returns:
        An already-connected :class:`PostgreSQLDriver`. Do not call ``.connect()``
        on it again.
    """
    return create_database_client_from_config_path(
        config_path,
        timeout=timeout,
        max_retries=max_retries,
        retry_delay=retry_delay,
        pool_size=pool_size,
    )
