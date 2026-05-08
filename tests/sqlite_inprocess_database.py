"""Shared SQLite test setup: DatabaseClient over InProcessRpcClient(RPCHandlers(driver)).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers

from tests.sqlite_legacy_schema_bootstrap import bootstrap_sqlite_schema_paths


def sqlite_inprocess_database_client(
    db_path: Path,
    *,
    backup_dir: Optional[Path] = None,
    driver_type: str = "sqlite",
) -> DatabaseClient:
    """Full app schema via legacy bootstrap, then RPC client on the same file.

    Caller must :meth:`DatabaseClient.disconnect`.

    Schema uses the historical bootstrap path so constraints match production (including
    ``UNIQUE (project_id, path)`` / watcher upserts). Opening only
    ``database_driver_pkg`` + ``sync_schema`` RPC does not reproduce that DDL.
    """
    backup = backup_dir or (db_path.parent / "backups")
    backup.mkdir(parents=True, exist_ok=True)
    resolved_db = db_path.resolve()
    resolved_backup = backup.resolve()
    driver_config = {
        "type": "sqlite",
        "config": {
            "path": str(resolved_db),
            "backup_dir": str(resolved_backup),
        },
    }
    path_str, backup_str = bootstrap_sqlite_schema_paths(
        driver_config,
        default_backup_dir=str(resolved_backup),
    )

    driver = create_driver(
        "sqlite",
        {"path": path_str, "backup_dir": backup_str},
    )
    handlers = RPCHandlers(driver)
    rpc = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=rpc, driver_type=driver_type)
    client.connect()
    return client
