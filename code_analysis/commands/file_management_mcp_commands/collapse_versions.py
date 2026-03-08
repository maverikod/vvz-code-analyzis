"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management import CollapseVersionsCommand

logger = logging.getLogger(__name__)


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
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
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
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        keep_latest: bool = True,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute collapse versions command.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            keep_latest: If True, keep latest version
            dry_run: If True, only show what would be collapsed

        Returns:
            SuccessResult with collapse statistics or ErrorResult on failure
        """
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            try:
                command = CollapseVersionsCommand(
                    database=database,
                    project_id=project_id,
                    keep_latest=keep_latest,
                    dry_run=dry_run,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "COLLAPSE_ERROR", "collapse_versions")

    @classmethod
    def metadata(cls: type["CollapseVersionsMCPCommand"]) -> Dict[str, Any]:
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
                "The collapse_versions command collapses file versions, keeping only the latest version "
                "by last_modified timestamp. It finds all database records with the same path but "
                "different last_modified timestamps and keeps only the latest one, deleting others "
                "with hard delete.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Finds all files with multiple versions (same path, different last_modified)\n"
                "5. For each file with multiple versions:\n"
                "   - Gets all versions sorted by last_modified (descending)\n"
                "   - If keep_latest=True: Keeps first version (latest), deletes others\n"
                "   - If keep_latest=False: Keeps last version (oldest), deletes others\n"
                "6. If dry_run=True:\n"
                "   - Lists files that would be collapsed\n"
                "   - Shows which versions would be kept/deleted\n"
                "7. If dry_run=False:\n"
                "   - Performs hard delete on old versions\n"
                "   - Removes all data for deleted versions\n"
                "8. Returns collapse statistics\n\n"
                "Version Collapsing:\n"
                "- Finds files with same path but different last_modified\n"
                "- Keeps latest version (by default) or oldest version\n"
                "- Hard deletes old versions (permanent removal)\n"
                "- Removes all data: file record, chunks, AST, vectors, entities\n\n"
                "Use cases:\n"
                "- Clean up duplicate file versions in database\n"
                "- Remove old versions after file updates\n"
                "- Reduce database size by removing redundant versions\n"
                "- Fix database inconsistencies with multiple versions\n\n"
                "Important notes:\n"
                "- Hard delete is PERMANENT and cannot be recovered\n"
                "- Always use dry_run=True first to preview changes\n"
                "- Default behavior keeps latest version (keep_latest=True)\n"
                "- Only collapses files with same path but different last_modified"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
                "keep_latest": {
                    "description": (
                        "If True, keeps latest version (by last_modified). Default is True. "
                        "If False, keeps oldest version instead."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be collapsed without actually collapsing. "
                        "Default is False. Always use dry_run=True first to preview changes."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview version collapse (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Lists all files with multiple versions that would be collapsed, "
                        "showing which versions would be kept and deleted."
                    ),
                },
                {
                    "description": "Collapse versions, keep latest",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "keep_latest": True,
                    },
                    "explanation": (
                        "Collapses file versions, keeping only the latest version by last_modified. "
                        "Permanently deletes old versions."
                    ),
                },
                {
                    "description": "Collapse versions, keep oldest",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "keep_latest": False,
                    },
                    "explanation": (
                        "Collapses file versions, keeping only the oldest version. "
                        "Permanently deletes newer versions."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "COLLAPSE_ERROR": {
                    "description": "General error during version collapse",
                    "example": "Database error, version retrieval error, or deletion failure",
                    "solution": (
                        "Check database integrity, verify file versions exist, "
                        "ensure database is not locked. Use dry_run=True first."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "kept_count": "Number of versions kept",
                        "deleted_count": "Number of versions deleted",
                        "collapsed_files": (
                            "List of files that were collapsed. Each entry contains:\n"
                            "- path: File path\n"
                            "- version_count: Number of versions found\n"
                            "- keep: Version that was kept (id, last_modified)\n"
                            "- delete: List of versions that were deleted (id, last_modified)"
                        ),
                        "dry_run": "Whether this was a dry run",
                        "message": "Status message",
                    },
                    "example": {
                        "kept_count": 1,
                        "deleted_count": 2,
                        "collapsed_files": [
                            {
                                "path": "src/main.py",
                                "version_count": 3,
                                "keep": {"id": 1, "last_modified": 1234567890.0},
                                "delete": [
                                    {"id": 2, "last_modified": 1234567800.0},
                                    {"id": 3, "last_modified": 1234567700.0},
                                ],
                            },
                        ],
                        "dry_run": False,
                        "message": "Collapsed 1 files: kept 1, deleted 2",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, COLLAPSE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Always use dry_run=True first to preview what would be collapsed",
                "Default keep_latest=True keeps the most recent version",
                "Use this command to clean up duplicate file versions",
                "Hard delete is permanent - backup database before running",
                "Run this command periodically to maintain database cleanliness",
            ],
        }
