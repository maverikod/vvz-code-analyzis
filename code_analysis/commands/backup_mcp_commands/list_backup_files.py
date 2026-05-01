"""
List backup files MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management.relative_path_list_pattern import (
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)
from ...core.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class ListBackupFilesMCPCommand(BaseMCPCommand):
    """List all backed up files."""

    name = "list_backup_files"
    version = "1.0.0"
    descr = (
        "List backed-up files in old_code; optional ``file_pattern`` / ``glob`` filter "
        "(fnmatch on project-relative paths, same semantics as list_project_files)"
    )
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
            "description": (
                "List each backed-up **original** path once (metadata from latest backup). "
                "Optional ``file_pattern`` / ``glob`` only. **No** ``limit``/``offset`` — the "
                "full filtered list is returned (unlike ``list_project_files``)."
            ),
            "properties": {
                **base_props,
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional filter: fnmatch on each backup ``file_path`` (project-relative "
                        "POSIX, ``*`` crosses ``/``). Literal without ``*?[]`` = exact path or "
                        "directory prefix. ``glob`` is an alias."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Alias of ``file_pattern``; non-empty ``file_pattern`` wins when both set."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_pattern: str | None = None,
        glob: str | None = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
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
                    file_info_with_details: Dict[str, Any] = dict(file_info)
                    file_info_with_details["command"] = backup_info.get("command", "")
                    related_raw = backup_info.get("related_files")
                    file_info_with_details["related_files"] = (
                        (related_raw.split(",") if isinstance(related_raw, str) else [])
                        if related_raw
                        else []
                    )
                    files_with_info.append(file_info_with_details)
                else:
                    files_with_info.append(file_info)

            eff = effective_listing_pattern(file_pattern, glob)
            if eff:
                files_with_info = [
                    row
                    for row in files_with_info
                    if relative_path_matches_listing_pattern(
                        str(row.get("file_path") or "").replace("\\", "/"),
                        eff,
                    )
                ]

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
                "Required: ``project_id``. Optional: ``file_pattern`` or ``glob`` to filter "
                "by project-relative path (fnmatch / directory-prefix, same rules as "
                "``list_project_files``). No pagination parameters — the full filtered set "
                "is returned."
            ),
            "detailed_description": (
                "The list_backup_files command retrieves all unique files that have been backed up "
                "in the project's old_code directory. It returns a list of file paths along with "
                "metadata from the latest backup version for each file.\n\n"
                "Operation flow:\n"
                "1. Resolves project root from ``project_id``\n"
                "2. Initializes BackupManager for the project\n"
                "3. Loads backup index from old_code/index.txt\n"
                "4. Extracts unique file paths from all backup entries\n"
                "5. For each file, finds the latest backup version\n"
                "6. Enriches file info with command name and related_files from latest backup\n"
                "7. Optionally filters rows where ``file_path`` matches ``file_pattern`` / ``glob`` "
                "(fnmatch on full relative path; literals without ``*?[]`` are directory prefixes)\n"
                "8. Returns list of files with metadata\n\n"
                "Backup System:\n"
                "- Backups are stored in old_code/ directory relative to the project root\n"
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
                "- File paths are relative to the project root\n"
                "- No ``limit``/``offset``: the full filtered list is returned in one response"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID (from create_project or list_projects). "
                        "Required; project root is resolved from the database."
                    ),
                    "type": "string",
                    "required": True,
                },
                "file_pattern": {
                    "description": (
                        "Optional fnmatch on each ``file_path`` (project-relative POSIX). "
                        "``glob`` is an alias; non-empty ``file_pattern`` wins when both are set."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["*.py", "code_analysis/commands/*", "docs/plans/foo"],
                },
                "glob": {
                    "description": "Alias of ``file_pattern``.",
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List all backed up files in project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": (
                        "Returns all unique files that have been backed up, "
                        "with metadata from their latest backup version."
                    ),
                },
                {
                    "description": "Only backups under a path prefix",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_pattern": "code_analysis/commands",
                    },
                    "explanation": (
                        "Literal prefix (no wildcards) keeps every ``file_path`` under that directory."
                    ),
                },
            ],
            "error_cases": {
                "LIST_BACKUP_FILES_ERROR": {
                    "description": "General error during backup file listing",
                    "example": (
                        "Unknown project_id, missing old_code directory, "
                        "corrupted index file, or permission errors"
                    ),
                    "solution": (
                        "Verify project is registered, project root exists and is accessible, "
                        "check old_code/index.txt integrity, ensure proper file permissions"
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
