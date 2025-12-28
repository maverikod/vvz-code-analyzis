"""
Base class for MCP commands with common functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult

from ..core.database import CodeDatabase
from ..core.exceptions import CodeAnalysisError, DatabaseError, ValidationError

logger = logging.getLogger(__name__)


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
        """
        Ensure SQLite physical integrity for a database file.

        If the database is corrupted, this method will:
        - create backup copies of the DB file (+ WAL/SHM/JOURNAL if present);
        - remove the corrupted DB file (+ sidecars);
        - allow subsequent initialization to recreate schema.

        Args:
            db_path: Path to SQLite database file.

        Returns:
            Dict with keys:
                ok: True if database is OK or was successfully recreated.
                repaired: True if recreation was performed.
                message: Human-readable summary.
                backup_paths: List of created backup file paths.
        """
        from ..core.db_integrity import ensure_sqlite_integrity_or_recreate

        result = ensure_sqlite_integrity_or_recreate(db_path, backup_dir=db_path.parent)
        return {
            "ok": result.ok,
            "repaired": result.repaired,
            "message": result.message,
            "backup_paths": list(result.backup_paths),
        }

    @staticmethod
    def _open_database(root_dir: str, auto_analyze: bool = True) -> CodeDatabase:
        """
        Open database connection for project.

        Automatically creates database and runs analysis if database doesn't exist
        or is empty.

        Args:
            root_dir: Project root directory
            auto_analyze: If True, automatically run analysis if DB is missing or empty

        Returns:
            CodeDatabase instance

        Raises:
            DatabaseError: If database cannot be opened or created
        """
        try:
            root_path = Path(root_dir).resolve()
            data_dir = root_path / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "code_analysis.db"

            integrity = BaseMCPCommand._ensure_database_integrity(db_path)
            if integrity.get("repaired"):
                logger.warning(
                    "SQLite corruption detected for %s; recreated. %s. Backups=%s",
                    db_path,
                    integrity.get("message"),
                    integrity.get("backup_paths"),
                )

            # Create database if it doesn't exist
            db_exists = db_path.exists()
            db = CodeDatabase(db_path)

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
                        assert db.conn is not None
                        cursor = db.conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM projects")
                        project_count = cursor.fetchone()[0]

                        if project_count == 0:
                            logger.info(
                                "Database exists but is empty, will run analysis"
                            )
                            needs_analysis = True
                        else:
                            cursor.execute("SELECT COUNT(*) FROM files")
                            file_count = cursor.fetchone()[0]
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

                    try:
                        asyncio.get_running_loop()
                        logger.info(
                            "Skipping auto-analysis in async context, will be triggered on first command"
                        )
                    except RuntimeError:
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                        cmd = UpdateIndexesMCPCommand()
                        result = loop.run_until_complete(
                            cmd.execute(
                                root_dir=str(root_path),
                                max_lines=400,
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
    def _get_project_id(
        db: CodeDatabase, root_path: Path, project_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get or create project ID.

        Args:
            db: Database instance
            root_path: Project root path
            project_id: Optional project ID; if provided, validates existence

        Returns:
            Project ID or None if project not found

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            if project_id:
                project = db.get_project(project_id)
                return project_id if project else None
            return db.get_or_create_project(str(root_path), name=root_path.name)
        except Exception as e:
            raise DatabaseError(
                f"Failed to get project ID: {str(e)}",
                operation="get_project_id",
                details={"root_path": str(root_path), "project_id": project_id},
            ) from e

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
            root_path = Path(root_dir).resolve()
            if not root_path.exists():
                raise ValidationError(
                    f"Root directory does not exist: {root_dir}",
                    field="root_dir",
                    details={"root_dir": root_dir},
                )
            if not root_path.is_dir():
                raise ValidationError(
                    f"Root directory is not a directory: {root_dir}",
                    field="root_dir",
                    details={"root_dir": root_dir},
                )
            return root_path
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
