"""
Clear all backups MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


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
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(self, project_id: str, **kwargs) -> SuccessResult | ErrorResult:
        """
        Clear all backups and history.

        Args:
            project_id: Project UUID.

        Returns:
            Success or error result
        """
        try:
            root_path = self._resolve_project_root(project_id)
            manager = BackupManager(root_path)

            success, message = manager.clear_all()

            if success:
                return SuccessResult(data={"message": message})
            else:
                return ErrorResult(message=message, code="CLEAR_BACKUPS_ERROR")
        except Exception as e:
            return self._handle_error(e, "CLEAR_BACKUPS_ERROR", "clear_all_backups")

    @classmethod
    def metadata(cls: type["ClearAllBackupsMCPCommand"]) -> Dict[str, Any]:
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
                "The clear_all_backups command permanently removes ALL backups and backup history "
                "from the project. It deletes all backup files from old_code/ directory and clears "
                "the backup index. This is a destructive operation that cannot be undone.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Initializes BackupManager for the project\n"
                "3. Ensures old_code/ directory exists (creates if needed)\n"
                "4. Deletes all files in old_code/ directory except index.txt\n"
                "5. Clears backup index by saving empty index to index.txt\n"
                "6. Returns success message\n\n"
                "Clearing Behavior:\n"
                "- ALL backup files are permanently deleted\n"
                "- Backup index is cleared (all entries removed)\n"
                "- old_code/ directory structure is preserved (directory not deleted)\n"
                "- index.txt file is reset to empty state\n"
                "- Operation cannot be undone\n"
                "- No backups remain after this operation\n\n"
                "Use cases:\n"
                "- Clean up project by removing all backup history\n"
                "- Free up disk space by deleting all backups\n"
                "- Reset backup system for a fresh start\n"
                "- Remove backups before archiving or sharing project\n"
                "- Clean up after successful project completion\n\n"
                "Important notes:\n"
                "- This operation is DESTRUCTIVE and PERMANENT\n"
                "- ALL backups are deleted - no way to restore files after this\n"
                "- Use with extreme caution - ensure backups are not needed\n"
                "- Consider backing up old_code/ directory before clearing if needed\n"
                "- After clearing, no files can be restored from backup history\n"
                "- old_code/ directory is not deleted, only its contents"
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
            },
            "usage_examples": [
                {
                    "description": "Clear all backups from project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Permanently deletes all backup files and clears backup history. "
                        "Use with caution - operation cannot be undone."
                    ),
                },
                {
                    "description": "Clean up backups in current directory",
                    "command": {
                        "root_dir": ".",
                    },
                    "explanation": (
                        "Removes all backups from the current working directory's project. "
                        "Frees up disk space but loses all backup history."
                    ),
                },
            ],
            "error_cases": {
                "CLEAR_BACKUPS_ERROR": {
                    "description": "Error during backup clearing",
                    "examples": [
                        {
                            "case": "Permission error",
                            "message": "Permission denied",
                            "solution": (
                                "Check file and directory permissions. Ensure write access "
                                "to old_code/ directory and index.txt file."
                            ),
                        },
                        {
                            "case": "Disk space issue",
                            "message": "No space left on device",
                            "solution": (
                                "Free up disk space. The operation needs space to write "
                                "the cleared index file."
                            ),
                        },
                        {
                            "case": "Directory access error",
                            "message": "Cannot access old_code directory",
                            "solution": (
                                "Verify old_code/ directory exists and is accessible. "
                                "Check directory permissions."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "All backups cleared successfully",
                    "data": {
                        "message": "Human-readable success message",
                    },
                    "example": {
                        "success": True,
                        "message": "All backups cleared",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., CLEAR_BACKUPS_ERROR)",
                    "message": "Human-readable error message explaining what went wrong",
                },
            },
            "best_practices": [
                "⚠️ WARNING: This operation is permanent and cannot be undone",
                "Verify no backups are needed before clearing",
                "Consider backing up old_code/ directory before clearing if you might need it",
                "Use this command only when you're certain backups are no longer needed",
                "After clearing, restore_backup_file will not work (no backups exist)",
                "Use list_backup_files first to see what will be deleted",
                "Consider using delete_backup for selective cleanup instead",
                "Use this for project cleanup or before archiving/sharing",
                "After clearing, new backups can still be created normally",
            ],
        }
