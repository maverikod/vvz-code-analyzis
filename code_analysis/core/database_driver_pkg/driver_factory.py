"""
Driver factory for creating database driver instances.

Strict universal-to-specific driver mapping: only driver types in the supported map
are resolved; all others raise DriverNotFoundError. No implicit fallbacks.

``sqlite_proxy`` uses the legacy IPC driver under :mod:`sqlite_proxy_legacy`
(:class:`~code_analysis.core.database_driver_pkg.sqlite_proxy_legacy.sqlite_proxy.SQLiteDriverProxy`).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Union

from .drivers.base import BaseDatabaseDriver
from .drivers.postgres import PostgreSQLDriver
from .drivers.sqlite import SQLiteDriver
from .exceptions import DriverNotFoundError
from .sqlite_proxy_legacy.sqlite_proxy import SQLiteDriverProxy

logger = logging.getLogger(__name__)

# Supported driver types: explicit map only. No hidden fallbacks.
_SUPPORTED_DRIVERS: Dict[str, type] = {
    "sqlite": SQLiteDriver,
    "postgres": PostgreSQLDriver,
    "sqlite_proxy": SQLiteDriverProxy,
}


def _normalize_driver_type(driver_type: str) -> str:
    """Normalize driver type for lookup: strip and lower-case."""
    if not driver_type or not isinstance(driver_type, str):
        return ""
    return driver_type.strip().lower()


def create_driver(
    driver_type: str,
    config: Dict[str, Any],
    *,
    connect: bool = True,
) -> Union[BaseDatabaseDriver, SQLiteDriverProxy]:
    """Create database driver instance.

    For ``sqlite`` and ``postgres``, returns :class:`BaseDatabaseDriver` from this
    package. For ``sqlite_proxy``, returns :class:`SQLiteDriverProxy` (legacy IPC
    contract).

    By default calls :meth:`~.connect` on the new instance. Pass ``connect=False``
    when the caller will connect (e.g. :class:`~code_analysis.core.database.base.CodeDatabase`
    connects once after construction).

    Driver type is validated against the supported map only. Unsupported values
    raise DriverNotFoundError.

    Args:
        driver_type: Driver type (``sqlite``, ``postgres``, ``sqlite_proxy``).
        config: Driver-specific configuration dictionary.
        connect: If True (default), call ``driver.connect(config)`` before return.

    Returns:
        Driver instance, connected unless ``connect=False``.

    Raises:
        DriverNotFoundError: If driver type is not in the supported map.
        RuntimeError: If direct ``sqlite`` is used outside worker/driver process
            (same guard as the former ``core.db_driver`` factory).
    """
    normalized = _normalize_driver_type(driver_type)
    if not normalized:
        raise DriverNotFoundError("Driver type is required and must be non-empty")

    if normalized not in _SUPPORTED_DRIVERS:
        supported = list(_SUPPORTED_DRIVERS.keys())
        raise DriverNotFoundError(
            f"Unknown driver type: {driver_type!r}. Supported: {supported}."
        )

    if normalized == "sqlite":
        is_worker = os.getenv("CODE_ANALYSIS_DB_WORKER", "0") == "1"
        is_driver = os.getenv("CODE_ANALYSIS_DB_DRIVER", "0") == "1"
        logger.info(
            "create_driver sqlite: is_worker=%s, is_driver=%s", is_worker, is_driver
        )
        if not is_worker and not is_driver:
            raise RuntimeError(
                "Direct SQLite driver can only be used in DB worker or DB driver process. "
                "Use sqlite_proxy driver instead."
            )

    driver_class = _SUPPORTED_DRIVERS[normalized]
    driver: Union[BaseDatabaseDriver, SQLiteDriverProxy] = driver_class()
    if connect:
        driver.connect(config)
    return driver
