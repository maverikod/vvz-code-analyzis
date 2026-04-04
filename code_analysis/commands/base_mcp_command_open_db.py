"""
Database open and integrity helpers for BaseMCPCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict

from ..core.constants import DEFAULT_REQUEST_TIMEOUT
from ..core.database_client.client import DatabaseClient
from ..core.exceptions import DatabaseError
from ..core.storage_paths import (
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)

logger = logging.getLogger(__name__)


def ensure_database_integrity(db_path: Path) -> Dict[str, Any]:
    """
    Ensure SQLite physical integrity for a database file.

    If corruption is detected, creates backups and writes a corruption marker.
    Does NOT recreate the DB automatically.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Dict with ok, repaired, message, backup_paths, marker_path.
    """
    from ..core.db_integrity import (
        backup_sqlite_files,
        check_sqlite_integrity,
        corruption_marker_path,
        read_corruption_marker,
        write_corruption_marker,
    )

    marker_path = corruption_marker_path(db_path)
    marker_data = read_corruption_marker(db_path)
    if marker_data is not None:
        msg = str(marker_data.get("message") or "Database is marked as corrupted")
        backups = marker_data.get("backup_paths")
        backup_paths: list[str] = []
        if isinstance(backups, list):
            backup_paths = [str(p) for p in backups]
        return {
            "ok": False,
            "repaired": False,
            "message": msg,
            "backup_paths": backup_paths,
            "marker_path": str(marker_path),
        }

    check = check_sqlite_integrity(db_path)
    if check.ok:
        return {
            "ok": True,
            "repaired": False,
            "message": check.message,
            "backup_paths": [],
            "marker_path": None,
        }

    backups = backup_sqlite_files(
        db_path, backup_dir=db_path.parent, include_sidecars=True
    )
    marker = write_corruption_marker(
        db_path,
        message=check.message,
        backup_paths=backups,
    )
    return {
        "ok": False,
        "repaired": False,
        "message": check.message,
        "backup_paths": list(backups),
        "marker_path": marker,
    }


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
        db_path = storage.db_path

        driver_type = (config_data.get("code_analysis") or {}).get("database") or {}
        if isinstance(driver_type, dict):
            driver_type = (driver_type.get("driver") or {}).get("type")
        else:
            driver_type = None
        if not isinstance(driver_type, str):
            driver_type = "unknown"
        logger.info(
            "DB entrypoint: universal chain -> specific(%s) -> RPC client -> isolated process",
            driver_type,
        )

        integrity = ensure_database_integrity(db_path)
        if integrity.get("ok") is False:
            try:
                from ..core.worker_manager import get_worker_manager

                stop_result = get_worker_manager().stop_all_workers(timeout=10.0)
                logger.warning(
                    "🛑 Stopped all workers due to corrupted database. %s",
                    stop_result.get("message"),
                )
            except Exception as e:
                logger.error(
                    "Failed to stop workers after corruption detection: %s",
                    e,
                    exc_info=True,
                )

            raise DatabaseError(
                "Database is corrupted and project is in safe mode. "
                "Only backup/restore/repair commands are allowed.",
                operation="database_corrupted",
                details={
                    "db_path": str(db_path),
                    "marker_path": integrity.get("marker_path"),
                    "backup_paths": integrity.get("backup_paths"),
                    "integrity_message": integrity.get("message"),
                    "allowed_commands": [
                        "get_database_corruption_status",
                        "backup_database",
                        "repair_sqlite_database",
                        "restore_database",
                        "list_backup_files",
                        "list_backup_versions",
                        "restore_backup_file",
                        "delete_backup",
                        "clear_all_backups",
                    ],
                },
            )

        socket_path = get_socket_path_fn(db_path)
        # Interactive MCP paths (e.g. repeat cst_save_tree) may wait on
        # sync_file_to_db_atomic or queue backlog; match DEFAULT_REQUEST_TIMEOUT.
        db = DatabaseClient(socket_path=socket_path, timeout=DEFAULT_REQUEST_TIMEOUT)
        db.connect()

        from ..core.database.base import get_schema_definition

        def _ensure_schema() -> None:
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

        try:
            db.select("code_content_fts", columns=["rowid"], limit=1)
        except Exception as e:
            err_msg = str(e).lower()
            cause_msg = str(getattr(e, "__cause__", "") or "").lower()
            if "no such table" in err_msg or "no such table" in cause_msg:
                logger.info(
                    "code_content_fts missing, running sync_schema for virtual tables"
                )
                try:
                    _ensure_schema()
                    logger.info("Virtual tables synced successfully")
                except Exception as sync_err:
                    logger.warning(
                        "Failed to sync virtual tables: %s",
                        sync_err,
                        exc_info=True,
                    )

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
