"""
Delete backup MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


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
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "backup_uuid": {
                    "type": "string",
                    "description": "UUID of backup to delete",
                },
            },
            "required": ["project_id", "backup_uuid"],
            "additionalProperties": False,
        }

    async def execute(
        self, project_id: str, backup_uuid: str, **kwargs
    ) -> SuccessResult | ErrorResult:
        """
        Delete backup from history.

        Args:
            project_id: Project UUID.
            backup_uuid: UUID of backup to delete.

        Returns:
            Success or error result
        """
        try:
            root_path = self._resolve_project_root(project_id)
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

    @classmethod
    def metadata(cls: type["DeleteBackupMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The delete_backup command permanently removes a specific backup from the backup "
                "system. It deletes both the backup file from old_code/ directory and removes "
                "the entry from the backup index.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Initializes BackupManager for the project\n"
                "3. Loads backup index from old_code/index.txt\n"
                "4. Verifies backup_uuid exists in index\n"
                "5. Locates backup file using UUID and file path from index\n"
                "6. Deletes backup file from old_code/ directory (if exists)\n"
                "7. Removes entry from backup index\n"
                "8. Saves updated index to disk\n"
                "9. Returns success message\n\n"
                "Deletion Behavior:\n"
                "- Backup file is permanently deleted from filesystem\n"
                "- Backup entry is removed from index\n"
                "- Operation cannot be undone\n"
                "- If backup file is missing but index entry exists, index is still cleaned\n"
                "- Other backups for the same file are not affected\n\n"
                "Use cases:\n"
                "- Remove old backup versions to save disk space\n"
                "- Clean up specific backup after successful restoration\n"
                "- Remove corrupted or invalid backups\n"
                "- Manage backup storage by deleting unnecessary versions\n\n"
                "Important notes:\n"
                "- Deletion is permanent and cannot be undone\n"
                "- Only the specified backup is deleted, other versions remain\n"
                "- If backup file is already missing, only index entry is removed\n"
                "- Use list_backup_versions to find backup UUIDs\n"
                "- Consider disk space implications before deleting backups"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain old_code/ directory with backups."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        ".",
                        "./code_analysis",
                    ],
                },
                "backup_uuid": {
                    "description": (
                        "UUID of the backup to delete. This is the unique identifier "
                        "assigned when the backup was created. Use list_backup_versions "
                        "to find available UUIDs for a file."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
                        "223e4567-e89b-12d3-a456-426614174001",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Delete a specific backup version",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": (
                        "Permanently deletes the backup identified by UUID. "
                        "Use list_backup_versions to find the UUID first."
                    ),
                },
                {
                    "description": "Remove old backup to free disk space",
                    "command": {
                        "root_dir": ".",
                        "backup_uuid": "223e4567-e89b-12d3-a456-426614174001",
                    },
                    "explanation": (
                        "Deletes an old backup version that is no longer needed, "
                        "freeing up disk space while keeping other versions."
                    ),
                },
            ],
            "error_cases": {
                "DELETE_BACKUP_ERROR": {
                    "description": "Error during backup deletion",
                    "examples": [
                        {
                            "case": "Backup UUID not found in index",
                            "message": "Backup {backup_uuid} not found in index",
                            "solution": (
                                "Verify backup_uuid is correct. Use list_backup_versions "
                                "or list_backup_files to find valid UUIDs. "
                                "UUID may have been already deleted."
                            ),
                        },
                        {
                            "case": "Permission error",
                            "message": "Permission denied",
                            "solution": (
                                "Check file and directory permissions. Ensure write access "
                                "to old_code/ directory and index.txt file."
                            ),
                        },
                        {
                            "case": "Index file corruption",
                            "message": "Error loading index",
                            "solution": (
                                "Backup index file may be corrupted. Check old_code/index.txt. "
                                "Consider using repair_database if available."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Backup deleted successfully",
                    "data": {
                        "message": "Human-readable success message with backup UUID",
                        "backup_uuid": "UUID of deleted backup",
                    },
                    "example": {
                        "success": True,
                        "message": "Backup 123e4567-e89b-12d3-a456-426614174000 deleted",
                        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., DELETE_BACKUP_ERROR)",
                    "message": "Human-readable error message explaining what went wrong",
                },
            },
            "best_practices": [
                "Use list_backup_versions first to identify which backup to delete",
                "Verify backup UUID is correct before deletion (operation is permanent)",
                "Consider keeping at least one backup version for important files",
                "Delete old backups to manage disk space, but keep recent ones",
                "After deletion, backup cannot be restored - ensure it's not needed",
                "If unsure, use list_backup_versions to see all available versions first",
                "Deletion only affects the specified backup, other versions remain safe",
            ],
        }
