"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .file_management import (
    CleanupDeletedFilesCommand,
    UnmarkDeletedFileCommand,
    CollapseVersionsCommand,
    RepairDatabaseCommand,
)

logger = logging.getLogger(__name__)


class CleanupDeletedFilesMCPCommand(BaseMCPCommand):
    """Clean up deleted files from database."""

    name = "cleanup_deleted_files"
    version = "1.0.0"
    descr = "Clean up deleted files from database (soft or hard delete)"
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, all projects",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be deleted",
                    "default": False,
                },
                "older_than_days": {
                    "type": "integer",
                    "description": "Only delete files deleted more than N days ago",
                },
                "hard_delete": {
                    "type": "boolean",
                    "description": "If True, permanently delete (removes physical file and all DB data)",
                    "default": False,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        older_than_days: Optional[int] = None,
        hard_delete: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute cleanup deleted files command.

        Args:
            root_dir: Root directory of the project
            project_id: Optional project UUID (all projects if None)
            dry_run: If True, only show what would be deleted
            older_than_days: Only delete files deleted more than N days ago
            hard_delete: If True, permanently delete

        Returns:
            SuccessResult with cleanup statistics or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir, auto_analyze=False)

            # Resolve project_id if not provided
            actual_project_id = None
            if project_id:
                actual_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not actual_project_id:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                    )

            try:
                command = CleanupDeletedFilesCommand(
                    database=database,
                    project_id=actual_project_id,
                    dry_run=dry_run,
                    older_than_days=older_than_days,
                    hard_delete=hard_delete,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "CLEANUP_ERROR", "cleanup_deleted_files")


class UnmarkDeletedFileMCPCommand(BaseMCPCommand):
    """Unmark file as deleted (recovery)."""

    name = "unmark_deleted_file"
    version = "1.0.0"
    descr = "Unmark file as deleted and restore from version directory"
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (current in version_dir or original_path)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be restored",
                    "default": False,
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute unmark deleted file command.

        Args:
            root_dir: Root directory of the project
            file_path: File path (current in version_dir or original_path)
            project_id: Optional project UUID
            dry_run: If True, only show what would be restored

        Returns:
            SuccessResult with restoration information or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir, auto_analyze=False)

            actual_project_id = self._get_project_id(database, root_path, project_id)
            if not actual_project_id:
                return ErrorResult(
                    message=(
                        f"Project not found: {project_id}"
                        if project_id
                        else "Failed to get or create project"
                    ),
                    code="PROJECT_NOT_FOUND",
                )

            try:
                command = UnmarkDeletedFileCommand(
                    database=database,
                    file_path=file_path,
                    project_id=actual_project_id,
                    dry_run=dry_run,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "UNMARK_ERROR", "unmark_deleted_file")


class CollapseVersionsMCPCommand(BaseMCPCommand):
    """Collapse file versions, keeping only latest."""

    name = "collapse_versions"
    version = "1.0.0"
    descr = "Collapse file versions, keeping only latest by last_modified"
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
                "keep_latest": {
                    "type": "boolean",
                    "description": "If True, keep latest version (default: True)",
                    "default": True,
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be collapsed",
                    "default": False,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        project_id: Optional[str] = None,
        keep_latest: bool = True,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute collapse versions command.

        Args:
            root_dir: Root directory of the project
            project_id: Optional project UUID
            keep_latest: If True, keep latest version
            dry_run: If True, only show what would be collapsed

        Returns:
            SuccessResult with collapse statistics or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir, auto_analyze=False)

            actual_project_id = self._get_project_id(database, root_path, project_id)
            if not actual_project_id:
                return ErrorResult(
                    message=(
                        f"Project not found: {project_id}"
                        if project_id
                        else "Failed to get or create project"
                    ),
                    code="PROJECT_NOT_FOUND",
                )

            try:
                command = CollapseVersionsCommand(
                    database=database,
                    project_id=actual_project_id,
                    keep_latest=keep_latest,
                    dry_run=dry_run,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "COLLAPSE_ERROR", "collapse_versions")


class RepairDatabaseMCPCommand(BaseMCPCommand):
    """Repair database integrity - restore correct file status based on actual file presence."""

    name = "repair_database"
    version = "1.0.0"
    descr = "Repair database integrity - restore correct file status based on actual file presence in project and versions"
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
                "version_dir": {
                    "type": "string",
                    "description": "Version directory for deleted files (default: data/versions)",
                    "default": "data/versions",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be repaired",
                    "default": False,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        project_id: Optional[str] = None,
        version_dir: str = "data/versions",
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute repair database command.

        Args:
            root_dir: Root directory of the project
            project_id: Optional project UUID
            version_dir: Version directory for deleted files
            dry_run: If True, only show what would be repaired

        Returns:
            SuccessResult with repair statistics or ErrorResult on failure
        """
        try:
            from pathlib import Path

            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir, auto_analyze=False)

            actual_project_id = self._get_project_id(database, root_path, project_id)
            if not actual_project_id:
                return ErrorResult(
                    message=(
                        f"Project not found: {project_id}"
                        if project_id
                        else "Failed to get or create project"
                    ),
                    code="PROJECT_NOT_FOUND",
                )

            # Resolve version_dir path
            if not Path(version_dir).is_absolute():
                version_dir = str(root_path / version_dir)

            try:
                command = RepairDatabaseCommand(
                    database=database,
                    project_id=actual_project_id,
                    root_dir=root_path,
                    version_dir=version_dir,
                    dry_run=dry_run,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "REPAIR_DATABASE_ERROR", "repair_database")
