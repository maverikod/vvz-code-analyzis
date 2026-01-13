"""
Driver factory for creating database driver instances.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from .drivers.base import BaseDatabaseDriver
from .drivers.sqlite import SQLiteDriver
from .exceptions import DriverNotFoundError


def create_driver(driver_type: str, config: Dict[str, Any]) -> BaseDatabaseDriver:
    """Create database driver instance.

    Args:
        driver_type: Driver type ('sqlite', 'postgres', 'mysql', etc.)
        config: Driver-specific configuration dictionary

    Returns:
        Driver instance

    Raises:
        DriverNotFoundError: If driver type is not found
    """
    driver_type_lower = driver_type.lower()

    if driver_type_lower == "sqlite":
        driver = SQLiteDriver()
        driver.connect(config)
        return driver
    elif driver_type_lower == "postgres":
        # Future implementation
        raise DriverNotFoundError(f"Driver type '{driver_type}' not yet implemented")
    elif driver_type_lower == "mysql":
        # Future implementation
        raise DriverNotFoundError(f"Driver type '{driver_type}' not yet implemented")
    else:
        raise DriverNotFoundError(f"Unknown driver type: {driver_type}")
