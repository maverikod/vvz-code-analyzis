"""
List backup versions MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


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
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Original file path (relative to project root)",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self, project_id: str, file_path: str, **kwargs
    ) -> SuccessResult | ErrorResult:
        """
        List all versions of a backed up file.

        Args:
            project_id: Project UUID.
            file_path: Original file path (relative to project root).

        Returns:
            List of versions with timestamp, size_bytes, size_lines
        """
        try:
            root_path = self._resolve_project_root(project_id)
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

    @classmethod
    def metadata(cls: type["ListBackupVersionsMCPCommand"]) -> Dict[str, Any]:
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
                "The list_backup_versions command retrieves all backup versions for a specific file. "
                "It returns detailed information about each backup including UUID, timestamp, file size, "
                "line count, command that created it, and related files.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Initializes BackupManager for the project\n"
                "3. Loads backup index from old_code/index.txt\n"
                "4. Searches index for all backups matching the file_path\n"
                "5. For each matching backup, verifies backup file exists\n"
                "6. Calculates file size in bytes and line count\n"
                "7. Extracts metadata (command, comment, related_files) from index\n"
                "8. Sorts versions by timestamp (newest first)\n"
                "9. Returns list of all versions with full details\n\n"
                "Version Information:\n"
                "- Each version has a unique UUID\n"
                "- Timestamp shows when backup was created (from file mtime)\n"
                "- size_bytes: File size in bytes\n"
                "- size_lines: Number of lines in file\n"
                "- command: Command that created this backup\n"
                "- comment: Optional comment/message from backup creation\n"
                "- related_files: List of files created/modified together\n\n"
                "Use cases:\n"
                "- View backup history for a specific file\n"
                "- Compare file sizes across versions\n"
                "- Find specific backup UUID for restoration\n"
                "- Understand what operations created each backup\n"
                "- Track file evolution over time\n\n"
                "Important notes:\n"
                "- File path must be relative to root_dir\n"
                "- Versions are sorted by timestamp (newest first)\n"
                "- Only backups with existing files are returned\n"
                "- If no backups found, returns empty list (count: 0)\n"
                "- Path matching is normalized (handles / and \\ separators)"
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
                        "Original file path relative to root_dir. This is the path of the file "
                        "as it existed when backed up. Use forward slashes or backslashes."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "code_analysis/core/backup_manager.py",
                        "src/utils.py",
                        "tests/test_backup.py",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "List all versions of a specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "code_analysis/core/backup_manager.py",
                    },
                    "explanation": (
                        "Returns all backup versions for backup_manager.py, "
                        "sorted by timestamp (newest first)."
                    ),
                },
                {
                    "description": "Check backup history for a file",
                    "command": {
                        "root_dir": ".",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Lists all backup versions of main.py to see its change history."
                    ),
                },
            ],
            "error_cases": {
                "LIST_BACKUP_VERSIONS_ERROR": {
                    "description": "General error during version listing",
                    "example": (
                        "Invalid root_dir, missing old_code directory, "
                        "corrupted index file, file_path not found, or permission errors"
                    ),
                    "solution": (
                        "Verify root_dir exists, check file_path is correct and relative to root_dir, "
                        "ensure old_code/index.txt is readable, check file permissions"
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "file_path": "Original file path that was queried",
                        "versions": (
                            "List of version dictionaries. Each contains:\n"
                            "- uuid: Backup UUID (use this for restore_backup_file)\n"
                            "- timestamp: Backup creation timestamp (YYYY-MM-DDTHH-MM-SS)\n"
                            "- size_bytes: File size in bytes\n"
                            "- size_lines: Number of lines in file\n"
                            "- command: Command that created this backup (optional)\n"
                            "- comment: Optional comment from backup creation\n"
                            "- related_files: List of related files (optional)"
                        ),
                        "count": "Number of backup versions found",
                    },
                    "example": {
                        "success": True,
                        "file_path": "code_analysis/core/backup_manager.py",
                        "versions": [
                            {
                                "uuid": "123e4567-e89b-12d3-a456-426614174000",
                                "timestamp": "2024-01-15T14-30-25",
                                "size_bytes": 15234,
                                "size_lines": 389,
                                "command": "compose_cst_module",
                                "comment": "Updated restore_file method",
                                "related_files": [],
                            },
                            {
                                "uuid": "223e4567-e89b-12d3-a456-426614174001",
                                "timestamp": "2024-01-14T10-15-30",
                                "size_bytes": 14890,
                                "size_lines": 375,
                                "command": "compose_cst_module",
                                "comment": "",
                                "related_files": [],
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., LIST_BACKUP_VERSIONS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use this command before restore_backup_file to find specific backup UUID",
                "Compare size_bytes and size_lines to see file changes",
                "Check command field to understand what operation created each backup",
                "Use timestamp to identify newest or oldest versions",
                "Use related_files to find files created together in refactoring operations",
                "First version in list (index 0) is always the newest",
            ],
        }
