"""
MCP commands for backup management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class ListBackupFilesMCPCommand(BaseMCPCommand):
    """List all backed up files."""

    name = "list_backup_files"
    version = "1.0.0"
    descr = "List all backed up files"
    category = "backup"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get command schema."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(self, root_dir: str, **kwargs) -> SuccessResult | ErrorResult:
        """
        List all backed up files.

        Args:
            root_dir: Project root directory

        Returns:
            List of backed up files
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            manager = BackupManager(root_path)

            files = manager.list_files()

            # Include command and related_files info
            index = manager._load_index()
            files_with_info = []
            for file_info in files:
                file_path = file_info["file_path"]
                # Find all backups for this file
                versions = manager.list_versions(file_path)
                if versions:
                    latest = versions[0]
                    backup_uuid = latest["uuid"]
                    backup_info = index.get(backup_uuid, {})
                    file_info_with_details = file_info.copy()
                    file_info_with_details["command"] = backup_info.get("command", "")
                    file_info_with_details["related_files"] = (
                        backup_info.get("related_files", "").split(",")
                        if backup_info.get("related_files")
                        else []
                    )
                    files_with_info.append(file_info_with_details)
                else:
                    files_with_info.append(file_info)

            return SuccessResult(
                data={
                    "files": files_with_info,
                    "count": len(files_with_info),
                }
            )
        except Exception as e:
            return self._handle_error(e, "LIST_BACKUP_FILES_ERROR", "list_backup_files")


class ListBackupVersionsMCPCommand(BaseMCPCommand):
    """List all versions of a backed up file."""

    name = "list_backup_versions"
    version = "1.0.0"
    descr = "List all versions of a backed up file"
    category = "backup"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get command schema."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
                "file_path": {
                    "type": "string",
                    "description": "Original file path (relative to root_dir)",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self, root_dir: str, file_path: str, **kwargs
    ) -> SuccessResult | ErrorResult:
        """
        List all versions of a backed up file.

        Args:
            root_dir: Project root directory
            file_path: Original file path (relative to root_dir)

        Returns:
            List of versions with timestamp, size_bytes, size_lines
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            manager = BackupManager(root_path)

            versions = manager.list_versions(file_path)

            return SuccessResult(
                data={
                    "file_path": file_path,
                    "versions": versions,
                    "count": len(versions),
                }
            )
        except Exception as e:
            return self._handle_error(
                e, "LIST_BACKUP_VERSIONS_ERROR", "list_backup_versions"
            )


class RestoreBackupFileMCPCommand(BaseMCPCommand):
    """Restore file from backup."""

    name = "restore_backup_file"
    version = "1.0.0"
    descr = "Restore file from backup"
    category = "backup"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get command schema."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
                "file_path": {
                    "type": "string",
                    "description": "Original file path (relative to root_dir)",
                },
                "backup_uuid": {
                    "type": "string",
                    "description": "UUID of backup to restore (optional, uses latest if not provided)",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        backup_uuid: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Restore file from backup.

        Args:
            root_dir: Project root directory
            file_path: Original file path (relative to root_dir)
            backup_uuid: UUID of backup to restore (optional, uses latest)

        Returns:
            Success or error result
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            manager = BackupManager(root_path)

            success, message = manager.restore_file(file_path, backup_uuid)

            if success:
                return SuccessResult(data={"message": message, "file_path": file_path})
            else:
                return ErrorResult(message=message, code="RESTORE_BACKUP_ERROR")
        except Exception as e:
            return self._handle_error(e, "RESTORE_BACKUP_ERROR", "restore_backup_file")


class DeleteBackupMCPCommand(BaseMCPCommand):
    """Delete backup from history."""

    name = "delete_backup"
    version = "1.0.0"
    descr = "Delete backup from history"
    category = "backup"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get command schema."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
                "backup_uuid": {
                    "type": "string",
                    "description": "UUID of backup to delete",
                },
            },
            "required": ["root_dir", "backup_uuid"],
            "additionalProperties": False,
        }

    async def execute(
        self, root_dir: str, backup_uuid: str, **kwargs
    ) -> SuccessResult | ErrorResult:
        """
        Delete backup from history.

        Args:
            root_dir: Project root directory
            backup_uuid: UUID of backup to delete

        Returns:
            Success or error result
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            manager = BackupManager(root_path)

            success, message = manager.delete_backup(backup_uuid)

            if success:
                return SuccessResult(
                    data={"message": message, "backup_uuid": backup_uuid}
                )
            else:
                return ErrorResult(message=message, code="DELETE_BACKUP_ERROR")
        except Exception as e:
            return self._handle_error(e, "DELETE_BACKUP_ERROR", "delete_backup")


class ClearAllBackupsMCPCommand(BaseMCPCommand):
    """Clear all backups and history."""

    name = "clear_all_backups"
    version = "1.0.0"
    descr = "Clear all backups and history"
    category = "backup"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get command schema."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(self, root_dir: str, **kwargs) -> SuccessResult | ErrorResult:
        """
        Clear all backups and history.

        Args:
            root_dir: Project root directory

        Returns:
            Success or error result
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            manager = BackupManager(root_path)

            success, message = manager.clear_all()

            if success:
                return SuccessResult(data={"message": message})
            else:
                return ErrorResult(message=message, code="CLEAR_BACKUPS_ERROR")
        except Exception as e:
            return self._handle_error(e, "CLEAR_BACKUPS_ERROR", "clear_all_backups")
