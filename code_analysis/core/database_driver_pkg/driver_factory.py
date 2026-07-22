"""
Driver factory for creating database driver instances.

Strict universal-to-specific driver mapping: only driver types in the supported map
are resolved; all others raise DriverNotFoundError. No implicit fallbacks.

SQLite support was removed; PostgreSQL is the only supported driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .drivers.base import BaseDatabaseDriver
from .drivers.postgres import PostgreSQLDriver
from .exceptions import DriverNotFoundError

logger = logging.getLogger(__name__)

# Supported driver types: explicit map only. No hidden fallbacks.
_SUPPORTED_DRIVERS: Dict[str, type] = {
    "postgres": PostgreSQLDriver,
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
) -> BaseDatabaseDriver:
    """Create database driver instance.

    Returns :class:`BaseDatabaseDriver` from this package (PostgreSQL only).

    By default calls :meth:`~.connect` on the new instance. Pass ``connect=False``
    when the caller will connect (e.g. :class:`~code_analysis.core.database.base.CodeDatabase`
    connects once after construction).

    Driver type is validated against the supported map only. Unsupported values
    raise DriverNotFoundError.

    Args:
        driver_type: Driver type (``postgres`` only).
        config: Driver-specific configuration dictionary.
        connect: If True (default), call ``driver.connect(config)`` before return.

    Returns:
        Driver instance, connected unless ``connect=False``.

    Raises:
        DriverNotFoundError: If driver type is not in the supported map.
    """
    normalized = _normalize_driver_type(driver_type)
    if not normalized:
        raise DriverNotFoundError("Driver type is required and must be non-empty")

    if normalized not in _SUPPORTED_DRIVERS:
        supported = list(_SUPPORTED_DRIVERS.keys())
        raise DriverNotFoundError(
            f"Unknown driver type: {driver_type!r}. Supported: {supported}. "
            "SQLite support was removed; PostgreSQL is required."
        )

    driver_class = _SUPPORTED_DRIVERS[normalized]
    driver: BaseDatabaseDriver = driver_class()
    if connect:
        driver.connect(config)
    return driver
