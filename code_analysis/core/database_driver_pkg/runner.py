"""
Database driver process runner.

Entry point for database driver process. Initializes driver, request queue,
and RPC server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .driver_factory import create_driver
from .drivers.base import BaseDatabaseDriver
from .exceptions import DriverConnectionError, DriverOperationError
from .request_queue import RequestQueue
from .rpc_server import RPCServer

# Set environment variable to indicate this is a driver process
os.environ["CODE_ANALYSIS_DB_DRIVER"] = "1"

logger = logging.getLogger(__name__)


def _setup_driver_logging(
    log_path: Optional[str] = None,
    max_bytes: int = 10485760,  # 10 MB default
    backup_count: int = 5,
) -> None:
    """Setup logging for driver process.

    Args:
        log_path: Path to driver log file (optional)
        max_bytes: Maximum log file size in bytes before rotation (default: 10 MB)
        backup_count: Number of backup log files to keep (default: 5)
    """
    if log_path:
        from logging.handlers import RotatingFileHandler

        log_file = Path(log_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger for driver process
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Rotating file handler for driver log
        file_handler = RotatingFileHandler(
            log_file,
            encoding="utf-8",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Also add console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)


def run_database_driver(
    driver_type: str,
    driver_config: Dict[str, Any],
    socket_path: str,
    log_path: Optional[str] = None,
    queue_max_size: int = 1000,
) -> None:
    """Run database driver process.

    This function runs in a separate process and handles database operations
    via RPC server. It initializes the driver, request queue, and RPC server,
    then processes requests in a loop.

    Args:
        driver_type: Driver type ('sqlite', 'postgres', 'mysql', etc.)
        driver_config: Driver-specific configuration dictionary
        socket_path: Path to Unix socket for RPC communication
        log_path: Path to driver log file (optional)
        queue_max_size: Maximum size of request queue (default: 1000)
    """
    # Setup logging
    _setup_driver_logging(log_path)

    logger.info(f"🚀 Database driver started: type={driver_type}, socket={socket_path}")

    driver: Optional[BaseDatabaseDriver] = None
    rpc_server: Optional[RPCServer] = None

    # Setup signal handlers for graceful shutdown
    shutdown_event = False

    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        nonlocal shutdown_event
        logger.info(f"Received signal {signum}, shutting down...")
        shutdown_event = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Create request queue
        request_queue = RequestQueue(max_size=queue_max_size)
        logger.info(f"Request queue initialized (max_size={queue_max_size})")

        # Create driver
        try:
            driver = create_driver(driver_type, driver_config)
            logger.info(f"Driver created: {driver_type}")
        except Exception as e:
            logger.error(f"Failed to create driver: {e}", exc_info=True)
            raise DriverConnectionError(f"Failed to create driver: {e}") from e

        # Create RPC server
        try:
            rpc_server = RPCServer(driver, request_queue, socket_path)
            logger.info("RPC server created")
        except Exception as e:
            logger.error(f"Failed to create RPC server: {e}", exc_info=True)
            raise DriverOperationError(f"Failed to create RPC server: {e}") from e

        # Start RPC server (runs in main thread)
        try:
            rpc_server.start()
        except Exception as e:
            logger.error(f"Failed to start RPC server: {e}", exc_info=True)
            raise DriverOperationError(f"Failed to start RPC server: {e}") from e

        # Wait for shutdown signal
        logger.info("Driver process running, waiting for requests...")
        while not shutdown_event:
            import time

            time.sleep(0.1)  # Small sleep to avoid busy waiting

    except KeyboardInterrupt:
        logger.info("Driver process interrupted by keyboard")
    except Exception as e:
        logger.error(f"Driver process crashed: {e}", exc_info=True)
    finally:
        logger.info("🛑 Driver process shutting down")
        try:
            if rpc_server:
                rpc_server.stop()
        except Exception:
            pass
        try:
            if driver:
                driver.disconnect()
        except Exception:
            pass
        logger.info("Driver process stopped")


if __name__ == "__main__":
    # For testing - can be called directly
    import json

    if len(sys.argv) < 4:
        print("Usage: runner.py <driver_type> <driver_config_json> <socket_path>")
        sys.exit(1)

    driver_type = sys.argv[1]
    driver_config = json.loads(sys.argv[2])
    socket_path = sys.argv[3]

    run_database_driver(driver_type, driver_config, socket_path)
