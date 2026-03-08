"""
Restore backup file MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


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
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Original file path (relative to project root)",
                },
                "backup_uuid": {
                    "type": "string",
                    "description": "UUID of backup to restore (optional, uses latest if not provided)",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        backup_uuid: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Restore file from backup.

        Args:
            project_id: Project UUID.
            file_path: Original file path (relative to project root).
            backup_uuid: UUID of backup to restore (optional, uses latest).

        Returns:
            Success or error result
        """
        try:
            root_path = self._resolve_project_root(project_id)
            manager = BackupManager(root_path)

            success, message = manager.restore_file(file_path, backup_uuid)

            if success:
                return SuccessResult(data={"message": message, "file_path": file_path})
            else:
                return ErrorResult(message=message, code="RESTORE_BACKUP_ERROR")
        except Exception as e:
            return self._handle_error(e, "RESTORE_BACKUP_ERROR", "restore_backup_file")

    @classmethod
    def metadata(cls: type["RestoreBackupFileMCPCommand"]) -> Dict[str, Any]:
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
                "The restore_backup_file command restores a file from a backup copy stored in "
                "the old_code directory. It can restore a specific backup version by UUID or "
                "automatically restore the latest version if no UUID is provided.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Initializes BackupManager for the project\n"
                "3. Loads backup index from old_code/index.txt\n"
                "4. Searches for backups matching the file_path\n"
                "5. If backup_uuid provided, finds that specific backup\n"
                "6. If backup_uuid not provided, selects latest backup (by timestamp)\n"
                "7. Verifies backup file exists in old_code/ directory\n"
                "8. Creates parent directories if needed\n"
                "9. Copies backup file to original location (overwrites existing file)\n"
                "10. Returns success message with backup UUID used\n\n"
                "Restoration Behavior:\n"
                "- If backup_uuid specified, restores that exact version\n"
                "- If backup_uuid omitted, restores latest version (newest timestamp)\n"
                "- Original file is overwritten (no backup of current file is created)\n"
                "- Parent directories are created automatically if missing\n"
                "- File permissions and metadata are preserved from backup\n\n"
                "Use cases:\n"
                "- Undo changes and restore previous version\n"
                "- Recover from accidental modifications\n"
                "- Restore specific version from history\n"
                "- Revert refactoring operations\n"
                "- Test different file versions\n\n"
                "Important notes:\n"
                "- Original file is overwritten without creating a new backup\n"
                "- If you want to preserve current file, create backup first\n"
                "- File path must be relative to root_dir\n"
                "- Backup file must exist in old_code/ directory\n"
                "- If no backups found for file, operation fails"
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
                "file_path": {
                    "description": (
                        "Original file path relative to root_dir. This is the path where "
                        "the file will be restored. Must match the path used when backup was created."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "code_analysis/core/backup_manager.py",
                        "src/utils.py",
                        "tests/test_backup.py",
                    ],
                },
                "backup_uuid": {
                    "description": (
                        "Optional UUID of specific backup to restore. If not provided, "
                        "restores the latest backup version (newest timestamp). "
                        "Use list_backup_versions to find available UUIDs."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
                        "223e4567-e89b-12d3-a456-426614174001",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Restore latest version of a file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "code_analysis/core/backup_manager.py",
                    },
                    "explanation": (
                        "Restores the most recent backup version of backup_manager.py. "
                        "Useful for undoing recent changes."
                    ),
                },
                {
                    "description": "Restore specific backup version",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "code_analysis/core/backup_manager.py",
                        "backup_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": (
                        "Restores a specific backup version identified by UUID. "
                        "Use list_backup_versions to find the UUID."
                    ),
                },
                {
                    "description": "Restore file after failed refactoring",
                    "command": {
                        "root_dir": ".",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Restores main.py to its latest backup state, "
                        "effectively undoing a failed refactoring operation."
                    ),
                },
            ],
            "error_cases": {
                "RESTORE_BACKUP_ERROR": {
                    "description": "Error during file restoration",
                    "examples": [
                        {
                            "case": "No backups found for file",
                            "message": "No backups found for {file_path}",
                            "solution": (
                                "Verify file_path is correct. Use list_backup_files to see "
                                "available files. Ensure backups exist in old_code/ directory."
                            ),
                        },
                        {
                            "case": "Backup UUID not found",
                            "message": "Backup {backup_uuid} not found",
                            "solution": (
                                "Verify backup_uuid is correct. Use list_backup_versions "
                                "to see available UUIDs for the file."
                            ),
                        },
                        {
                            "case": "Backup file missing",
                            "message": "Backup file not found: {backup_path}",
                            "solution": (
                                "Backup file was deleted or moved. Check old_code/ directory. "
                                "Index may be out of sync with actual files."
                            ),
                        },
                        {
                            "case": "Permission error",
                            "message": "Permission denied",
                            "solution": (
                                "Check file and directory permissions. Ensure write access "
                                "to target location and read access to backup file."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "File restored successfully",
                    "data": {
                        "message": "Human-readable success message with backup UUID",
                        "file_path": "Path of restored file (relative to root_dir)",
                    },
                    "example": {
                        "success": True,
                        "message": "File restored from backup 123e4567-e89b-12d3-a456-426614174000",
                        "file_path": "code_analysis/core/backup_manager.py",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., RESTORE_BACKUP_ERROR)",
                    "message": "Human-readable error message explaining what went wrong",
                },
            },
            "best_practices": [
                "Use list_backup_versions first to see available backup versions",
                "If unsure which version, omit backup_uuid to restore latest",
                "Consider creating a backup of current file before restoring (if needed)",
                "Use specific backup_uuid for precise version control",
                "Verify file after restoration to ensure it's correct",
                "Check related_files in backup metadata to restore related files if needed",
                "After restoration, file is overwritten - changes are lost",
            ],
        }
