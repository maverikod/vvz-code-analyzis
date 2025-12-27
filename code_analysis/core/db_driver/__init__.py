"""
Database driver factory and registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from .base import BaseDatabaseDriver
from .sqlite import SQLiteDriver
from .sqlite_proxy import SQLiteDriverProxy

logger = logging.getLogger(__name__)

# Driver registry
_DRIVERS: Dict[str, type[BaseDatabaseDriver]] = {
    "sqlite": SQLiteDriver,
    "sqlite_proxy": SQLiteDriverProxy,
}


def register_driver(name: str, driver_class: type[BaseDatabaseDriver]) -> None:
    """
    Register a new database driver.

    Args:
        name: Driver name
        driver_class: Driver class (subclass of BaseDatabaseDriver)
    """
    if not issubclass(driver_class, BaseDatabaseDriver):
        raise TypeError("Driver class must be a subclass of BaseDatabaseDriver")
    _DRIVERS[name] = driver_class
    logger.info(f"Registered database driver: {name}")


def create_driver(driver_name: str, config: Dict[str, Any]) -> BaseDatabaseDriver:
    """
    Create and initialize database driver.

    Args:
        driver_name: Name of the driver (e.g., 'sqlite', 'sqlite_proxy')
                     For 'sqlite', checks config for 'use_proxy' flag
        config: Driver-specific configuration
                - For 'sqlite': can include 'use_proxy' boolean to use proxy driver
                - For 'sqlite_proxy': can include 'worker_config' dict

    Returns:
        Initialized driver instance

    Raises:
        ValueError: If driver name is not registered
        RuntimeError: If driver initialization fails
    """
    # Handle automatic proxy selection for sqlite driver
    if driver_name == "sqlite":
        use_proxy = config.get("use_proxy", False)
        if use_proxy:
            logger.info("Using proxy driver for sqlite (use_proxy=True)")
            driver_name = "sqlite_proxy"
            # Extract worker_config if present
            worker_config = config.get("worker_config", {})
            # Keep other config but add worker_config
            proxy_config = {k: v for k, v in config.items() if k != "use_proxy"}
            if worker_config:
                proxy_config["worker_config"] = worker_config
            config = proxy_config

    if driver_name not in _DRIVERS:
        available = ", ".join(_DRIVERS.keys())
        raise ValueError(
            f"Unknown database driver: {driver_name}. "
            f"Available drivers: {available}"
        )

    driver_class = _DRIVERS[driver_name]
    logger.info(f"Creating database driver: {driver_name}")

    try:
        driver = driver_class()
        driver.connect(config)
        logger.info(f"Database driver '{driver_name}' initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize database driver '{driver_name}': {e}")
        raise RuntimeError(f"Database driver initialization failed: {e}") from e


def get_available_drivers() -> list[str]:
    """
    Get list of available driver names.

    Returns:
        List of driver names
    """
    return list(_DRIVERS.keys())
