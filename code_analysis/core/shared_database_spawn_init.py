"""
Ensure shared database is initialized in spawn child processes.

At import time we only connect if the driver socket already exists (e.g. worker
process). The main server process does not connect here; it starts the driver
in main() and then sets shared_database. So the server can start fully first,
then start the driver, then connect.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path

from code_analysis.commands.base_mcp_command import (
    BaseMCPCommand,
    _get_socket_path_from_db_path,
)
from code_analysis.commands.base_mcp_command_open_db import (
    open_database_from_config_impl,
)

from .shared_database import (
    close_shared_database,
    is_shared_database_current_process,
    set_shared_database,
)

logger = logging.getLogger(__name__)


def ensure_shared_database_for_current_process() -> None:
    """Open a process-local shared DB client when a child process is spawned."""
    if is_shared_database_current_process():
        return

    close_shared_database()
    db = open_database_from_config_impl(
        BaseMCPCommand._resolve_config_path,
        _get_socket_path_from_db_path,
        auto_analyze=False,
    )
    set_shared_database(db)
    logger.info("Shared database initialized for child process")


def _driver_socket_path() -> Path | None:
    """Return driver socket path from config, or None if config cannot be read."""
    try:
        storage = BaseMCPCommand._get_shared_storage()
        return Path(_get_socket_path_from_db_path(storage.db_path))
    except Exception:
        return None


# Run only when the driver is already running (socket exists and accept connections).
# Main server process skips: socket missing, or connect fails (stale socket / driver not up).
# Main will start the driver and set shared_database in main().
_socket = _driver_socket_path()
if _socket is not None and _socket.exists():
    try:
        ensure_shared_database_for_current_process()
    except Exception as e:
        logger.debug(
            "Connect at import skipped (main process or stale socket): %s; shared_database will be set in main().",
            e,
        )
else:
    logger.debug(
        "Driver socket not present at import (main process); shared_database will be set in main() after driver start."
    )
