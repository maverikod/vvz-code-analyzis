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
        driver_name: Name of the driver (e.g., 'sqlite', 'sqlite_proxy', 'mysql', 'postgres')
        config: Driver-specific configuration
                - For 'sqlite_proxy': can include 'worker_config' dict

    Returns:
        Initialized driver instance

    Raises:
        ValueError: If driver name is not registered
        RuntimeError: If driver initialization fails
    """
    logger.info(f"[create_driver] Called with driver_name={driver_name}, config_keys={list(config.keys())}")
    import os

    # Direct sqlite driver can only be used in DB worker process
    if driver_name == "sqlite":
        is_worker = os.getenv("CODE_ANALYSIS_DB_WORKER", "0") == "1"
        logger.info(f"[create_driver] sqlite driver check: is_worker={is_worker}")
        if not is_worker:
            logger.error(
                "Direct 'sqlite' driver can only be used in DB worker process. "
                "Use 'sqlite_proxy' driver instead."
            )
            raise RuntimeError(
                "Direct SQLite driver can only be used in DB worker process. "
                "Use sqlite_proxy driver instead."
            )

    if driver_name not in _DRIVERS:
        available = ", ".join(_DRIVERS.keys())
        logger.error(f"[create_driver] Unknown driver: {driver_name}, available: {available}")
        raise ValueError(
            f"Unknown database driver: {driver_name}. "
            f"Available drivers: {available}"
        )

    driver_class = _DRIVERS[driver_name]
    logger.info(f"[create_driver] Creating database driver: {driver_name}, class={driver_class}")

    try:
        logger.info(f"[create_driver] Instantiating driver class")
        print(f"[create_driver] Instantiating driver class", flush=True)
        driver = driver_class()
        logger.info(f"[create_driver] Driver instance created, calling connect() with config")
        print(f"[create_driver] Driver instance created, calling connect() with config", flush=True)
        driver.connect(config)
        logger.info(f"[create_driver] Database driver '{driver_name}' initialized successfully")
        print(f"[create_driver] Database driver '{driver_name}' initialized successfully", flush=True)
        return driver
    except Exception as e:
        logger.error(f"[create_driver] Failed to initialize database driver '{driver_name}': {e}", exc_info=True)
        print(f"[create_driver] Failed to initialize database driver '{driver_name}': {e}", flush=True, file=__import__('sys').stderr)
        raise RuntimeError(f"Database driver initialization failed: {e}") from e


def get_available_drivers() -> list[str]:
    """
    Get list of available driver names.

    Returns:
        List of driver names
    """
    return list(_DRIVERS.keys())
