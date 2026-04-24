"""
Driver factory for creating database driver instances.

Strict universal-to-specific driver mapping: only driver types in the supported map
are resolved; all others raise DriverNotFoundError. No implicit fallbacks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from .drivers.base import BaseDatabaseDriver
from .drivers.postgres import PostgreSQLDriver
from .drivers.sqlite import SQLiteDriver
from .exceptions import DriverNotFoundError

# Supported driver types: explicit map only. No hidden fallbacks.
_SUPPORTED_DRIVERS: Dict[str, type[BaseDatabaseDriver]] = {
    "sqlite": SQLiteDriver,
    "postgres": PostgreSQLDriver,
}


def _normalize_driver_type(driver_type: str) -> str:
    """Normalize driver type for lookup: strip and lower-case."""
    if not driver_type or not isinstance(driver_type, str):
        return ""
    return driver_type.strip().lower()


def create_driver(driver_type: str, config: Dict[str, Any]) -> BaseDatabaseDriver:
    """Create database driver instance.

    Driver type is validated against the supported map only. Unsupported or
    ambiguous values raise DriverNotFoundError. No implicit default driver.

    Args:
        driver_type: Driver type ('sqlite', 'postgres' supported).
        config: Driver-specific configuration dictionary.

    Returns:
        Connected driver instance.

    Raises:
        DriverNotFoundError: If driver type is not in the supported map.
    """
    normalized = _normalize_driver_type(driver_type)
    if not normalized:
        raise DriverNotFoundError("Driver type is required and must be non-empty")

    if normalized not in _SUPPORTED_DRIVERS:
        supported = list(_SUPPORTED_DRIVERS.keys())
        raise DriverNotFoundError(
            f"Unknown driver type: {driver_type!r}. Supported: {supported}."
        )

    driver_class = _SUPPORTED_DRIVERS[normalized]
    driver: BaseDatabaseDriver = driver_class()
    driver.connect(config)
    return driver
