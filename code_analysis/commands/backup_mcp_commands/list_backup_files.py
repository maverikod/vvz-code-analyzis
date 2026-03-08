"""
List backup files MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.backup_manager import BackupManager

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
        List all backed up files.

        Args:
            project_id: Project UUID.

        Returns:
            List of backed up files
        """
        try:
            root_path = self._resolve_project_root(project_id)
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

    @classmethod
    def metadata(cls: type["ListBackupFilesMCPCommand"]) -> Dict[str, Any]:
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
            "parameters_summary": (
                "Required: project_id. No limit or other optional parameters."
            ),
            "detailed_description": (
                "The list_backup_files command retrieves all unique files that have been backed up "
                "in the project's old_code directory. It returns a list of file paths along with "
                "metadata from the latest backup version for each file.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Initializes BackupManager for the project\n"
                "3. Loads backup index from old_code/index.txt\n"
                "4. Extracts unique file paths from all backup entries\n"
                "5. For each file, finds the latest backup version\n"
                "6. Enriches file info with command name and related_files from latest backup\n"
                "7. Returns list of files with metadata\n\n"
                "Backup System:\n"
                "- Backups are stored in old_code/ directory relative to root_dir\n"
                "- Each backup has a UUID and is indexed in old_code/index.txt\n"
                "- Backup filename format: path_with_underscores-UUID\n"
                "- Index format: UUID|File Path|Timestamp|Command|Related Files|Comment\n\n"
                "Use cases:\n"
                "- Discover all files that have been backed up\n"
                "- Check which files were modified by specific commands\n"
                "- Find files that were part of refactoring operations\n"
                "- Audit backup history\n\n"
                "Important notes:\n"
                "- Returns unique file paths (one entry per file, not per backup)\n"
                "- Each file entry includes metadata from its latest backup\n"
                "- command field shows which command created the latest backup\n"
                "- related_files field shows files created/modified together (e.g., from split operations)\n"
                "- Empty backup directory returns empty list (count: 0)\n"
                "- File paths are relative to root_dir"
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
                    "description": "List all backed up files in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns all unique files that have been backed up, "
                        "with metadata from their latest backup version."
                    ),
                },
                {
                    "description": "Check backups in current directory",
                    "command": {
                        "root_dir": ".",
                    },
                    "explanation": (
                        "Lists all backed up files in the current working directory's project."
                    ),
                },
            ],
            "error_cases": {
                "LIST_BACKUP_FILES_ERROR": {
                    "description": "General error during backup file listing",
                    "example": (
                        "Invalid root_dir, missing old_code directory, "
                        "corrupted index file, or permission errors"
                    ),
                    "solution": (
                        "Verify root_dir exists and is accessible, check old_code/index.txt "
                        "file integrity, ensure proper file permissions"
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "files": (
                            "List of file dictionaries. Each contains:\n"
                            "- file_path: Original file path (relative to root_dir)\n"
                            "- command: Name of command that created latest backup (optional)\n"
                            "- related_files: List of related files (e.g., from split operations, optional)"
                        ),
                        "count": "Number of unique backed up files",
                    },
                    "example": {
                        "success": True,
                        "files": [
                            {
                                "file_path": "code_analysis/core/backup_manager.py",
                                "command": "compose_cst_module",
                                "related_files": [],
                            },
                            {
                                "file_path": "code_analysis/commands/refactor.py",
                                "command": "split_file_to_package",
                                "related_files": [
                                    "code_analysis/commands/refactor/base.py",
                                    "code_analysis/commands/refactor/split.py",
                                ],
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., LIST_BACKUP_FILES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use this command to discover what files have been modified",
                "Check command field to understand what operations created backups",
                "Use related_files to find files created together (e.g., from splits)",
                "Combine with list_backup_versions to see all backup versions for a file",
                "Use before restore_backup_file to find available files to restore",
            ],
        }
