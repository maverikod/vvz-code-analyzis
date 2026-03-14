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
    load_raw_config,
    resolve_storage_paths,
)
from ..core.shared_database import get_shared_database
from .base_mcp_command_open_db import ensure_database_integrity
from .base_mcp_command_resolve_path import resolve_file_path_from_project

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
        """Ensure SQLite physical integrity; delegates to open_db module."""
        return ensure_database_integrity(db_path)

    @staticmethod
    def _open_database_from_config(auto_analyze: bool = False) -> DatabaseClient:
        """Return the shared long-lived database client (no per-command open)."""
        return get_shared_database()

    def _open_database(
        self: "BaseMCPCommand",
        root_dir: Optional[str] = None,
        auto_analyze: bool = False,
    ) -> DatabaseClient:
        """Open database via universal entrypoint only (config-based). root_dir is ignored; no path selection."""
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
    def _get_raw_config() -> Dict[str, Any]:
        """
        Load raw config dict from active server config path.

        Returns:
            Full config dict (e.g. for code_analysis.git_commit_on_write).
        """
        config_path = BaseMCPCommand._resolve_config_path()
        return load_raw_config(config_path)

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
        """Resolve absolute file path from project_id and relative path."""
        return resolve_file_path_from_project(database, project_id, relative_file_path)

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
