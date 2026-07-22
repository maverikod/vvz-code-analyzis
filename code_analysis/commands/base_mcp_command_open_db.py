"""
Database open and integrity helpers for BaseMCPCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict

from ..core.config import get_driver_config
from ..core.constants import DEFAULT_REQUEST_TIMEOUT
from ..core.database_client.factory import create_database_client_from_config_path
from ..core.database_client.client import DatabaseClient
from ..core.exceptions import DatabaseError
from ..core.storage_paths import (
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)

logger = logging.getLogger(__name__)


def _schema_def_to_driver_format(schema_def: Dict[str, Any]) -> Dict[str, Any]:
    """Convert get_schema_definition() output to driver sync_schema format."""
    tables = schema_def.get("tables")
    if not isinstance(tables, dict):
        return schema_def
    tables_list = []
    for k, v in tables.items():
        t = {"name": k, **v}
        cols = t.get("columns") or []
        t["columns"] = [
            {
                **c,
                "nullable": not c.get("not_null", False),
                "type": (
                    "INTEGER" if c.get("type") == "BOOLEAN" else c.get("type", "TEXT")
                ),
            }
            for c in cols
        ]
        fks = t.pop("foreign_keys", [])
        t["constraints"] = [
            {
                "type": "foreign_key",
                "columns": c.get("columns", []),
                "references_table": c.get("references_table", ""),
                "references_columns": c.get("references_columns", []),
            }
            for c in fks
        ]
        tables_list.append(t)
    return {**schema_def, "tables": tables_list}


def open_database_once_for_shared(
    resolve_config_path_fn: Callable[[], Path],
    get_socket_path_fn: Callable[[Path], str],
) -> DatabaseClient:
    """
    Open database and run integrity check, connect, and probe selects once.

    Called once at server startup to establish the long-lived connection;
    do not call per-command. Resolves config, ensures integrity, creates
    DatabaseClient, connect(), runs two probe selects and sync_schema if needed.

    Args:
        resolve_config_path_fn: Callable that returns config path.
        get_socket_path_fn: Callable(db_path) -> socket path.

    Returns:
        Connected DatabaseClient instance.

    Raises:
        DatabaseError: On integrity failure, connect failure, or probe failure.
    """
    try:
        config_path = resolve_config_path_fn()
        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        ensure_storage_dirs(storage)

        dc = get_driver_config(config_data)
        driver_type = (dc or {}).get("type") if isinstance(dc, dict) else "postgres"

        logger.info(
            "DB entrypoint: driver=%s -> in-process RPCHandlers + PostgreSQL (no Unix RPC)",
            driver_type,
        )

        _ = get_socket_path_fn  # API compatibility; factory derives transport from config
        # Interactive MCP paths (e.g. repeat cst_save_tree) may wait on
        # sync_file_to_db_atomic or queue backlog; match DEFAULT_REQUEST_TIMEOUT.
        db = create_database_client_from_config_path(
            config_path, timeout=DEFAULT_REQUEST_TIMEOUT
        )
        db.connect()

        try:
            db.execute("SELECT 1", None)
        except Exception as e:
            raise DatabaseError(
                f"PostgreSQL connection probe failed: {e}",
                operation="open_database",
                details={"error": str(e)},
            ) from e

        from ..core.database.base import get_schema_definition

        def _ensure_schema() -> None:
            """Return ensure schema."""
            schema_def = get_schema_definition()
            schema_def = _schema_def_to_driver_format(schema_def)
            backup_dir = getattr(storage, "backup_dir", None)
            db.sync_schema(
                schema_def,
                backup_dir=str(backup_dir) if backup_dir else None,
            )

        try:
            db.select("projects", columns=["id"], limit=1)
        except Exception as e:
            err_msg = str(e).lower()
            cause_msg = str(getattr(e, "__cause__", "") or "").lower()
            if (
                "no such table" in err_msg
                or "no such table" in repr(e).lower()
                or "no such table" in cause_msg
            ):
                logger.info(
                    "Database has no tables, initializing schema via sync_schema"
                )
                try:
                    _ensure_schema()
                    logger.info("Schema initialized successfully")
                    db.select("projects", columns=["id"], limit=1)
                except Exception as schema_err:
                    logger.warning(
                        "Failed to initialize schema: %s",
                        schema_err,
                        exc_info=True,
                    )
                    raise DatabaseError(
                        f"Schema init failed (empty DB): {schema_err}",
                        operation="sync_schema",
                        details={"error": str(schema_err)},
                    ) from schema_err
            else:
                raise

        return db
    except DatabaseError:
        raise
    except Exception as e:
        raise DatabaseError(
            f"Failed to open database: {str(e)}",
            operation="open_database",
            details={"error": str(e)},
        ) from e


def open_database_from_config_impl(
    resolve_config_path_fn: Callable[[], Path],
    get_socket_path_fn: Callable[[Path], str],
    auto_analyze: bool = False,
) -> DatabaseClient:
    """
    Open database connection via config (universal driver chain).

    Delegates to open_database_once_for_shared so workers and tests get
    the same integrity/connect/probe behaviour. For the server process,
    prefer calling open_database_once_for_shared once at startup.

    Args:
        resolve_config_path_fn: Callable that returns config path.
        get_socket_path_fn: Callable(db_path) -> socket path.
        auto_analyze: Unused; for API compatibility.

    Returns:
        DatabaseClient instance.

    Raises:
        DatabaseError: If database cannot be opened or is corrupted.
    """
    _ = auto_analyze
    return open_database_once_for_shared(resolve_config_path_fn, get_socket_path_fn)
