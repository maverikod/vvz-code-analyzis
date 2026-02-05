"""
Base class for MCP commands with common functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.database_client.client import DatabaseClient
from ..core.constants import DEFAULT_DB_DRIVER_SOCKET_DIR
from ..core.exceptions import (
    CodeAnalysisError,
    DatabaseError,
    ValidationError,
)
from ..core.storage_paths import (
    StoragePaths,
    ensure_storage_dirs,
    load_raw_config,
    resolve_storage_paths,
)

logger = logging.getLogger(__name__)


def _get_socket_path_from_db_path(db_path: Path) -> str:
    """Get socket path for database driver from database path.

    Args:
        db_path: Path to database file

    Returns:
        Socket path string
    """
    db_name = db_path.stem
    socket_dir = Path(DEFAULT_DB_DRIVER_SOCKET_DIR)
    socket_dir.mkdir(parents=True, exist_ok=True)
    return str(socket_dir / f"{db_name}_driver.sock")


class BaseMCPCommand(Command):
    """
    Base class for MCP commands with common functionality.

    Provides:
    - Database connection management
    - Project ID resolution
    - Standardized error handling
    - Common validation methods

    Notes:
        This base class also includes a SQLite physical integrity check.
        If the database file is corrupted (e.g. "database disk image is malformed"),
        it is backed up and recreated automatically.
    """

    @staticmethod
    def _ensure_database_integrity(db_path: Path) -> Dict[str, Any]:
        """Ensure SQLite physical integrity for a database file.

        Notes:
            If corruption is detected, this method:
            - creates filesystem backups of the DB file (+ sidecars);
            - writes a persistent corruption marker next to the DB.

            It does NOT attempt to recreate the DB automatically. Once a project is
            marked corrupted, DB-dependent commands must be blocked until explicit
            repair/restore.

        Args:
            db_path: Path to SQLite database file.

        Returns:
            Dict with keys:
                ok: True only if DB is OK and not blocked by a marker.
                repaired: Always False here (repair is explicit via separate commands).
                message: Human-readable summary.
                backup_paths: List of created backup file paths (if any).
                marker_path: Corruption marker path if present/created.
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

    @staticmethod
    def _open_database_from_config(auto_analyze: bool = False) -> DatabaseClient:
        """Open database connection using server config only.

        Database path is resolved from server configuration (config.json).
        No project root or root_dir is used.

        Args:
            auto_analyze: If True, run analysis when DB is empty (unused when opening from config).

        Returns:
            DatabaseClient instance.

        Raises:
            DatabaseError: If database cannot be opened or created.
        """
        try:
            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            ensure_storage_dirs(storage)
            db_path = storage.db_path

            integrity = BaseMCPCommand._ensure_database_integrity(db_path)
            if integrity.get("ok") is False:
                # Stop all workers aggressively: they must not operate on corrupted DB.
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

                marker_path = integrity.get("marker_path")
                backup_paths = integrity.get("backup_paths")
                raise DatabaseError(
                    "Database is corrupted and project is in safe mode. "
                    "Only backup/restore/repair commands are allowed.",
                    operation="database_corrupted",
                    details={
                        "db_path": str(db_path),
                        "marker_path": marker_path,
                        "backup_paths": backup_paths,
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

            socket_path = _get_socket_path_from_db_path(db_path)
            db = DatabaseClient(socket_path=socket_path)
            db.connect()

            # Ensure schema exists (empty DB after delete-and-recreate has no tables)
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
                        from ..core.database.base import get_schema_definition

                        schema_def = get_schema_definition()
                        # Driver expects tables as list; columns use "nullable" (we have "not_null"); constraints from foreign_keys
                        tables = schema_def.get("tables")
                        if isinstance(tables, dict):
                            tables_list = []
                            for k, v in tables.items():
                                t = {"name": k, **v}
                                cols = t.get("columns") or []
                                t["columns"] = [
                                    {
                                        **c,
                                        "nullable": not c.get("not_null", False),
                                        "type": (
                                            "INTEGER"
                                            if c.get("type") == "BOOLEAN"
                                            else c.get("type", "TEXT")
                                        ),
                                    }
                                    for c in cols
                                ]
                                fks = t.pop("foreign_keys", [])
                                t["constraints"] = [
                                    {
                                        "type": "foreign_key",
                                        "columns": c.get("columns", []),
                                        "references_table": c.get(
                                            "references_table", ""
                                        ),
                                        "references_columns": c.get(
                                            "references_columns", []
                                        ),
                                    }
                                    for c in fks
                                ]
                                tables_list.append(t)
                            schema_def = {**schema_def, "tables": tables_list}
                        backup_dir = getattr(storage, "backup_dir", None)
                        db.sync_schema(
                            schema_def,
                            backup_dir=str(backup_dir) if backup_dir else None,
                        )
                        logger.info("Schema initialized successfully")
                        # Verify schema: retry select so we do not return with broken DB
                        db.select("projects", columns=["id"], limit=1)
                    except Exception as schema_err:
                        logger.warning(
                            "Failed to initialize schema: %s", schema_err, exc_info=True
                        )
                        raise DatabaseError(
                            f"Schema init failed (empty DB): {schema_err}",
                            operation="sync_schema",
                            details={"error": str(schema_err)},
                        ) from schema_err
                else:
                    raise

            # Ensure virtual tables (e.g. code_content_fts) exist (older DBs may lack them)
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
                        from ..core.database.base import get_schema_definition

                        schema_def = get_schema_definition()
                        tables = schema_def.get("tables")
                        if isinstance(tables, dict):
                            tables_list = []
                            for k, v in tables.items():
                                t = {"name": k, **v}
                                cols = t.get("columns") or []
                                t["columns"] = [
                                    {
                                        **c,
                                        "nullable": not c.get("not_null", False),
                                        "type": (
                                            "INTEGER"
                                            if c.get("type") == "BOOLEAN"
                                            else c.get("type", "TEXT")
                                        ),
                                    }
                                    for c in cols
                                ]
                                fks = t.pop("foreign_keys", [])
                                t["constraints"] = [
                                    {
                                        "type": "foreign_key",
                                        "columns": c.get("columns", []),
                                        "references_table": c.get(
                                            "references_table", ""
                                        ),
                                        "references_columns": c.get(
                                            "references_columns", []
                                        ),
                                    }
                                    for c in fks
                                ]
                                tables_list.append(t)
                            schema_def = {**schema_def, "tables": tables_list}
                        backup_dir = getattr(storage, "backup_dir", None)
                        db.sync_schema(
                            schema_def,
                            backup_dir=str(backup_dir) if backup_dir else None,
                        )
                        logger.info("Virtual tables synced successfully")
                    except Exception as sync_err:
                        logger.warning(
                            "Failed to sync virtual tables: %s", sync_err, exc_info=True
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

    def _open_database(
        self: "BaseMCPCommand",
        root_dir: Optional[str] = None,
        auto_analyze: bool = False,
    ) -> DatabaseClient:
        """Open database from server config. root_dir is ignored (use project_id and _resolve_project_root)."""
        return BaseMCPCommand._open_database_from_config(auto_analyze=auto_analyze)

    @staticmethod
    def _get_project_id_by_root_path(
        db: DatabaseClient, root_path: str
    ) -> Optional[str]:
        """Get project ID by root path (for internal use e.g. project_creation)."""
        rows = db.select("projects", where={"root_path": root_path}, columns=["id"])
        if rows:
            return rows[0].get("id")
        return None

    @staticmethod
    def _get_project_id(
        db: DatabaseClient, root_path: Path, project_id: Optional[str] = None
    ) -> Optional[str]:
        """Resolve or create project ID. Prefer passing project_id and using _resolve_project_root."""
        if project_id:
            project = db.get_project(project_id)
            if project:
                return project_id
            existing = BaseMCPCommand._get_project_id_by_root_path(db, str(root_path))
            if existing and existing != project_id:
                raise ValidationError(
                    "Project root is already registered with a different project_id",
                    field="project_id",
                    details={
                        "root_path": str(root_path),
                        "existing_project_id": existing,
                        "provided_project_id": project_id,
                    },
                )
            project_name = root_path.name
            result = db.execute(
                "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
                (project_id, str(root_path), project_name),
            )
            affected = 0
            if isinstance(result, dict):
                data = result.get("data", result)
                affected = data.get("affected_rows", 0) if isinstance(data, dict) else 0
            if affected == 0:
                raise DatabaseError(
                    "Failed to create project",
                    operation="create_project",
                    details={"project_id": project_id, "root_path": str(root_path)},
                )
            return project_id
        existing_id = BaseMCPCommand._get_project_id_by_root_path(db, str(root_path))
        if existing_id:
            return existing_id
        new_id = str(uuid.uuid4())
        result = db.execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (new_id, str(root_path), root_path.name),
        )
        affected = 0
        if isinstance(result, dict):
            data = result.get("data", result)
            affected = data.get("affected_rows", 0) if isinstance(data, dict) else 0
        if affected == 0:
            raise DatabaseError(
                "Failed to create project",
                operation="create_project",
                details={"root_path": str(root_path)},
            )
        return new_id

    @staticmethod
    def _resolve_config_path() -> Path:
        """
        Resolve active server config path.

        Priority:
        - mcp_proxy_adapter global config (cfg.config_path)
        - cwd/config.json
        """

        try:
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            cfg_path = getattr(cfg, "config_path", None)
            if isinstance(cfg_path, str) and cfg_path.strip():
                return Path(cfg_path).expanduser().resolve()
        except Exception:
            pass

        return (Path.cwd() / "config.json").resolve()

    @staticmethod
    def _get_shared_storage() -> StoragePaths:
        """
        Resolve shared storage paths from application config (one DB for all projects).

        Returns:
            StoragePaths with db_path, backup_dir, etc. from server config.
        """
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = load_raw_config(config_path)
        return resolve_storage_paths(config_data=config_data, config_path=config_path)

    @staticmethod
    def _resolve_project_root(project_id: str) -> Path:
        """
        Resolve project root directory from project_id (database only).

        Args:
            project_id: Project ID (UUID4). Root path is resolved from projects table.

        Returns:
            Resolved absolute Path to project root.

        Raises:
            ValidationError: If project_id not provided or project not found.
        """
        from ..core.exceptions import ValidationError

        if not project_id:
            raise ValidationError(
                "project_id is required",
                field="project_id",
                details={},
            )
        db = BaseMCPCommand._open_database_from_config()
        try:
            project = db.get_project(project_id)
            if not project:
                raise ValidationError(
                    f"Project with ID {project_id} not found in database",
                    field="project_id",
                    details={"project_id": project_id},
                )
            root_path = Path(project.root_path)
            if not root_path.exists():
                raise ValidationError(
                    f"Project root path does not exist: {root_path}",
                    field="project_id",
                    details={"project_id": project_id, "root_path": str(root_path)},
                )
            return root_path
        finally:
            db.disconnect()

    @staticmethod
    def _validate_file_path(file_path: str, root_path: Path) -> Path:
        """
        Validate and resolve file path relative to root.

        Args:
            file_path: File path (absolute or relative)
            root_path: Project root path

        Returns:
            Resolved Path object

        Raises:
            ValidationError: If file path is invalid
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = root_path / file_path_obj

            if not file_path_obj.exists():
                raise ValidationError(
                    f"File does not exist: {file_path}",
                    field="file_path",
                    details={"file_path": file_path, "resolved": str(file_path_obj)},
                )

            if not file_path_obj.is_file():
                raise ValidationError(
                    f"Path is not a file: {file_path}",
                    field="file_path",
                    details={"file_path": file_path, "resolved": str(file_path_obj)},
                )

            return file_path_obj
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                f"Invalid file path: {str(e)}",
                field="file_path",
                details={"file_path": file_path, "error": str(e)},
            ) from e

    @staticmethod
    def _resolve_file_path_from_project(
        database: DatabaseClient,
        project_id: str,
        relative_file_path: str,
    ) -> Path:
        """
        Resolve absolute file path from project_id and relative path.

        Path formation: watch_dir_path / project_name / relative_file_path

        Args:
            database: DatabaseClient instance
            project_id: Project identifier (UUID4)
            relative_file_path: File path relative to project root

        Returns:
            Resolved absolute Path object

        Raises:
            ValidationError: If project not found, watch_dir not found, or path invalid
        """
        # Get project from database
        project = database.get_project(project_id)
        if not project:
            raise ValidationError(
                f"Project with ID {project_id} not found in database",
                field="project_id",
                details={"project_id": project_id},
            )

        if not project.watch_dir_id:
            raise ValidationError(
                f"Project {project_id} is not linked to a watch directory",
                field="project_id",
                details={"project_id": project_id, "project_name": project.name},
            )

        if not project.name:
            raise ValidationError(
                f"Project {project_id} does not have a name",
                field="project_id",
                details={"project_id": project_id},
            )

        # Get watch_dir_path from database
        watch_dir_path_result = database.execute(
            "SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ?",
            (project.watch_dir_id,),
        )
        # execute may return list directly (DataResult) or dict with "data" key
        if isinstance(watch_dir_path_result, list):
            watch_dir_paths = watch_dir_path_result
        else:
            watch_dir_paths = watch_dir_path_result.get("data", [])

        if not watch_dir_paths:
            raise ValidationError(
                f"Watch directory path not found for watch_dir_id {project.watch_dir_id}",
                field="project_id",
                details={
                    "project_id": project_id,
                    "watch_dir_id": project.watch_dir_id,
                },
            )

        # Each row is a dict with column names as keys
        watch_dir_path = watch_dir_paths[0].get("absolute_path")
        if not watch_dir_path:
            raise ValidationError(
                f"Watch directory path is NULL for watch_dir_id {project.watch_dir_id}",
                field="project_id",
                details={
                    "project_id": project_id,
                    "watch_dir_id": project.watch_dir_id,
                },
            )

        # Form absolute path: watch_dir_path / project_name / relative_file_path
        absolute_path = Path(watch_dir_path) / project.name / relative_file_path
        resolved_path = absolute_path.resolve()

        # Verify path exists
        if not resolved_path.exists():
            raise ValidationError(
                f"File does not exist: {resolved_path}",
                field="file_path",
                details={
                    "relative_file_path": relative_file_path,
                    "absolute_path": str(resolved_path),
                    "watch_dir_path": watch_dir_path,
                    "project_name": project.name,
                },
            )

        return resolved_path

    def _handle_error(
        self: "BaseMCPCommand", error: Exception, error_code: str, operation: str = None
    ) -> ErrorResult:
        """
        Handle exception and convert to ErrorResult.

        Args:
            self: Command instance.
            error: Exception that occurred
            error_code: Error code for the result
            operation: Optional operation name for logging

        Returns:
            ErrorResult with error information
        """
        operation_str = f" ({operation})" if operation else ""
        logger.exception(f"Command failed{operation_str}: {error}")

        if isinstance(error, CodeAnalysisError):
            details = error.details.copy()
            details["error_type"] = type(error).__name__
            if hasattr(error, "operation") and error.operation:
                details["operation"] = error.operation
            if hasattr(error, "field") and error.field:
                details["field"] = error.field

            return ErrorResult(
                message=error.message,
                code=error.code or error_code,
                details=details,
            )

        return ErrorResult(
            message=str(error),
            code=error_code,
            details={"error_type": type(error).__name__, "error": str(error)},
        )

    @classmethod
    def _get_base_schema_properties(cls: type["BaseMCPCommand"]) -> Dict[str, Any]:
        """
        Get base schema properties common to most commands.

        Args:
            cls: Command class.

        Returns:
            Dictionary with common schema properties
        """
        return {
            "project_id": {
                "type": "string",
                "description": "Project UUID (from create_project or list_projects). Required for commands that operate on a project.",
            },
        }
