"""
Base class for MCP commands with common functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.database_client.client import DatabaseClient
from ..core.constants import DEFAULT_DB_DRIVER_SOCKET_DIR
from ..core.exceptions import (
    CodeAnalysisError,
    DatabaseError,
    ProjectIdError,
    ValidationError,
)
from ..core.project_resolution import normalize_root_dir
from ..core.project_resolution import require_matching_project_id
from ..core.storage_paths import (
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
    def _open_database(root_dir: str, auto_analyze: bool = True) -> DatabaseClient:
        """Open database connection for project.

        Automatically creates database and runs analysis if database doesn't exist
        or is empty.

        IMPORTANT:
            If the database file is detected as corrupted, the project is put into
            "safe mode" and DB-dependent commands are blocked until explicit
            repair/restore.

        Args:
            root_dir: Project root directory.
            auto_analyze: If True, automatically run analysis if DB is missing or empty.

        Returns:
            DatabaseClient instance.

        Raises:
            DatabaseError: If database cannot be opened or created.
        """
        try:
            # Root path is still needed for diagnostics and for auto-analysis entrypoints.
            root_path = normalize_root_dir(root_dir)

            # NOTE:
            # `root_dir` is a watched project root (source directory),
            # but DB is service state and MUST NOT be created inside watched dirs.
            # Resolve DB path from server config.
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
                        "root_dir": str(root_path),
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

            # Create database if it doesn't exist
            db_exists = db_path.exists()

            # Get socket path for database driver
            socket_path = _get_socket_path_from_db_path(db_path)

            # Create DatabaseClient instance
            db = DatabaseClient(socket_path=socket_path)
            db.connect()

            # Check if database is empty (no projects or no files)
            if auto_analyze:
                needs_analysis = False
                if not db_exists:
                    logger.info(
                        f"Database not found at {db_path}, will create and analyze"
                    )
                    needs_analysis = True
                else:
                    try:
                        # Use DatabaseClient API - check projects count
                        projects = db.select("projects", columns=["id"], limit=1)
                        project_count = len(projects)

                        if project_count == 0:
                            logger.info(
                                "Database exists but is empty, will run analysis"
                            )
                            needs_analysis = True
                        else:
                            # Check files count
                            files = db.select("files", columns=["id"], limit=1)
                            file_count = len(files)
                            if file_count == 0:
                                logger.info(
                                    "Database exists but has no files, will run analysis"
                                )
                                needs_analysis = True
                    except Exception as e:
                        logger.warning(
                            f"Error checking database contents: {e}, will run analysis"
                        )
                        needs_analysis = True

                if needs_analysis:
                    logger.info(f"Running automatic project analysis for {root_path}")
                    try:
                        from .code_mapper_mcp_command import UpdateIndexesMCPCommand
                    except ImportError:
                        logger.warning(
                            "UpdateIndexesMCPCommand not available, skipping auto-analysis"
                        )
                        return db

                    import asyncio
                    import threading

                    # Try to queue the indexing command if we're in async context
                    try:
                        asyncio.get_running_loop()
                        # We're in async context - start indexing in background thread
                        logger.info(
                            f"Starting automatic project analysis for {root_path} in background thread (async context)"
                        )

                        def run_indexing():
                            """Run indexing in background thread."""
                            try:
                                from ..core.constants import DEFAULT_MAX_FILE_LINES

                                # Create new event loop for this thread
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)

                                try:
                                    cmd = UpdateIndexesMCPCommand()
                                    result = loop.run_until_complete(
                                        cmd.execute(
                                            root_dir=str(root_path),
                                            max_lines=DEFAULT_MAX_FILE_LINES,
                                        )
                                    )

                                    if not result.success:
                                        logger.warning(
                                            f"Automatic analysis completed with warnings: {result.message}"
                                        )
                                    else:
                                        logger.info(
                                            "Automatic analysis completed successfully: %s files processed",
                                            (
                                                result.data.get("files_processed", 0)
                                                if result.data
                                                else 0
                                            ),
                                        )
                                finally:
                                    loop.close()
                            except Exception as e:
                                logger.error(
                                    f"Failed to run automatic indexing in background thread: {e}",
                                    exc_info=True,
                                )

                        thread = threading.Thread(target=run_indexing, daemon=True)
                        thread.start()
                        logger.info(
                            f"Started background indexing thread for {root_path}"
                        )
                    except RuntimeError:
                        # No running loop - can run synchronously
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                        from ..core.constants import DEFAULT_MAX_FILE_LINES

                        cmd = UpdateIndexesMCPCommand()
                        result = loop.run_until_complete(
                            cmd.execute(
                                root_dir=str(root_path),
                                max_lines=DEFAULT_MAX_FILE_LINES,
                            )
                        )

                        if not result.success:
                            logger.warning(
                                f"Automatic analysis completed with warnings: {result.message}"
                            )
                        else:
                            logger.info(
                                "Automatic analysis completed successfully: %s files processed",
                                (
                                    result.data.get("files_processed", 0)
                                    if result.data
                                    else 0
                                ),
                            )

            return db
        except DatabaseError:
            raise
        except Exception as e:
            raise DatabaseError(
                f"Failed to open database: {str(e)}",
                operation="open_database",
                details={"root_dir": str(root_dir), "error": str(e)},
            ) from e

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
    def _require_project_id_gate(root_dir: str, project_id: Optional[str]) -> str:
        """
        Enforce mutating-command safety gate against `<root_dir>/projectid`.

        Args:
            root_dir: Project root directory.
            project_id: Provided project_id.

        Returns:
            Validated project_id.
        """

        try:
            return require_matching_project_id(root_dir, project_id)
        except ProjectIdError as e:
            raise ValidationError(
                str(e),
                field="project_id",
                details={"root_dir": str(root_dir), "project_id": project_id},
            ) from e

    @staticmethod
    def _get_project_id(
        db: DatabaseClient, root_path: Path, project_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get or create project ID.

        Args:
            db: DatabaseClient instance
            root_path: Project root path
            project_id: Optional project ID; if provided, validates existence

        Returns:
            Project ID or None if project not found

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            if project_id:
                # Check if project with this ID exists
                project = db.get_project(project_id)
                if project:
                    # Project exists - return it without checking root_path match
                    # This allows using project_id with any root_dir (e.g., server root_dir)
                    # The actual project root_path is stored in the database
                    return project_id

                # Project doesn't exist - check if root_path is already registered
                existing = BaseMCPCommand._get_project_id_by_root_path(
                    db, str(root_path)
                )
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

                # Create project with specified ID using execute for SQL functions
                project_name = root_path.name
                result = db.execute(
                    "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
                    (project_id, str(root_path), project_name),
                )
                # Verify insertion succeeded
                # execute() returns dict with "data" key containing {"affected_rows": ..., "lastrowid": ...}
                # or directly {"affected_rows": ..., "lastrowid": ...} depending on response format
                affected_rows = 0
                if isinstance(result, dict):
                    if "data" in result and isinstance(result["data"], dict):
                        affected_rows = result["data"].get("affected_rows", 0)
                    else:
                        affected_rows = result.get("affected_rows", 0)
                if affected_rows == 0:
                    raise DatabaseError(
                        "Failed to create project: no rows affected",
                        operation="create_project",
                        details={"project_id": project_id, "root_path": str(root_path)},
                    )
                return project_id

            # Non-mutating commands may still infer/create.
            return BaseMCPCommand._get_or_create_project(
                db, str(root_path), root_path.name
            )
        except Exception as e:
            raise DatabaseError(
                f"Failed to get project ID: {str(e)}",
                operation="get_project_id",
                details={"root_path": str(root_path), "project_id": project_id},
            ) from e

    @staticmethod
    def _get_project_id_by_root_path(
        db: DatabaseClient, root_path: str
    ) -> Optional[str]:
        """Get project ID by root path.

        Args:
            db: DatabaseClient instance
            root_path: Project root path

        Returns:
            Project ID or None if not found
        """
        rows = db.select("projects", where={"root_path": root_path}, columns=["id"])
        if rows:
            return rows[0].get("id")
        return None

    @staticmethod
    def _get_or_create_project(
        db: DatabaseClient, root_path: str, name: Optional[str] = None
    ) -> str:
        """Get or create project by root path.

        Args:
            db: DatabaseClient instance
            root_path: Project root path
            name: Optional project name

        Returns:
            Project ID (UUID4 string)
        """
        # Check if project exists
        existing_id = BaseMCPCommand._get_project_id_by_root_path(db, root_path)
        if existing_id:
            return existing_id

        # Create new project using execute for SQL functions
        project_id = str(uuid.uuid4())
        project_name = name or Path(root_path).name

        result = db.execute(
            "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
            (project_id, root_path, project_name),
        )
        # Verify insertion succeeded
        # execute() returns dict with "data" key containing {"affected_rows": ..., "lastrowid": ...}
        # or directly {"affected_rows": ..., "lastrowid": ...} depending on response format
        affected_rows = 0
        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], dict):
                affected_rows = result["data"].get("affected_rows", 0)
            else:
                affected_rows = result.get("affected_rows", 0)
        if affected_rows == 0:
            raise DatabaseError(
                "Failed to create project: no rows affected",
                operation="create_project",
                details={"root_path": root_path},
            )
        return project_id

    @staticmethod
    def _get_or_create_dataset(
        db: DatabaseClient, project_id: str, root_path: str, name: Optional[str] = None
    ) -> str:
        """Get or create dataset by project_id and root_path.

        Datasets support multi-root indexing within a project.
        Each dataset represents a separate indexed root directory.

        Args:
            db: DatabaseClient instance
            project_id: Project ID (UUID4 string)
            root_path: Root directory path (will be normalized to absolute)
            name: Optional dataset name

        Returns:
            Dataset ID (UUID4 string)
        """
        # Normalize root_path to absolute resolved path
        normalized_root = str(normalize_root_dir(root_path))

        # Check if dataset exists
        result = db.execute(
            "SELECT id FROM datasets WHERE project_id = ? AND root_path = ?",
            (project_id, normalized_root),
        )
        # Handle both dict and list results from execute()
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict):
            data = result.get("data", [])
        else:
            data = []
        if data:
            return data[0]["id"]

        # Create new dataset
        dataset_id = str(uuid.uuid4())
        dataset_name = name or Path(normalized_root).name
        result = db.execute(
            """
            INSERT INTO datasets (id, project_id, root_path, name, updated_at)
            VALUES (?, ?, ?, ?, julianday('now'))
            """,
            (dataset_id, project_id, normalized_root, dataset_name),
        )
        # Verify insertion succeeded
        affected_rows = 0
        if isinstance(result, dict):
            if "data" in result and isinstance(result["data"], dict):
                affected_rows = result["data"].get("affected_rows", 0)
            else:
                affected_rows = result.get("affected_rows", 0)
        if affected_rows == 0:
            raise DatabaseError(
                "Failed to create dataset: no rows affected",
                operation="create_dataset",
                details={"project_id": project_id, "root_path": normalized_root},
            )
        logger.info(
            f"Created dataset {dataset_id} for project {project_id} at {normalized_root}"
        )
        return dataset_id

    @staticmethod
    def _get_dataset_id(
        db: DatabaseClient, project_id: str, root_path: str
    ) -> Optional[str]:
        """Get dataset ID by project_id and root_path.

        Args:
            db: DatabaseClient instance
            project_id: Project ID (UUID4 string)
            root_path: Root directory path (will be normalized to absolute)

        Returns:
            Dataset ID (UUID4 string) or None if not found
        """
        normalized_root = str(normalize_root_dir(root_path))
        result = db.execute(
            "SELECT id FROM datasets WHERE project_id = ? AND root_path = ?",
            (project_id, normalized_root),
        )
        # Handle both dict and list results from execute()
        if isinstance(result, list):
            data = result
        elif isinstance(result, dict):
            data = result.get("data", [])
        else:
            data = []
        return data[0]["id"] if data else None

    @staticmethod
    def _resolve_project_root(
        project_id: Optional[str] = None, root_dir: Optional[str] = None
    ) -> Path:
        """
        Resolve project root directory from project_id or root_dir.

        Args:
            project_id: Optional project ID (UUID4). If provided, root_dir will be resolved from database.
            root_dir: Optional project root directory. Required if project_id is not provided.

        Returns:
            Resolved absolute Path to project root.

        Raises:
            ValidationError: If neither project_id nor root_dir is provided, or if project not found.
        """
        from ..core.exceptions import ValidationError
        from ..core.project_resolution import normalize_root_dir

        if project_id:
            # Resolve root_dir from project_id via database
            # Use server root_dir to open database
            from ..core.storage_paths import (
                load_raw_config,
                resolve_storage_paths,
            )

            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            storage = resolve_storage_paths(
                config_data=config_data, config_path=config_path
            )
            db_path = storage.db_path

            # Get socket path and create DatabaseClient
            socket_path = _get_socket_path_from_db_path(db_path)
            db = DatabaseClient(socket_path=socket_path)
            db.connect()

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
                # Disconnect from database client
                db.disconnect()
        elif root_dir:
            return normalize_root_dir(root_dir)
        else:
            raise ValidationError(
                "Either project_id or root_dir must be provided",
                field="project_id",
                details={},
            )

    @staticmethod
    def _validate_root_dir(root_dir: str) -> Path:
        """
        Validate and resolve root directory.

        Args:
            root_dir: Root directory path

        Returns:
            Resolved Path object

        Raises:
            ValidationError: If root directory is invalid
        """
        try:
            return normalize_root_dir(root_dir)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                f"Invalid root directory: {str(e)}",
                field="root_dir",
                details={"root_dir": root_dir, "error": str(e)},
            ) from e

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
            "root_dir": {
                "type": "string",
                "description": "Project root directory (contains data/code_analysis.db)",
            },
            "project_id": {
                "type": "string",
                "description": "Optional project UUID; if omitted, inferred by root_dir",
            },
        }
