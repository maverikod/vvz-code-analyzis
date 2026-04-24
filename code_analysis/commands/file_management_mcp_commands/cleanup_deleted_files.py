"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management import CleanupDeletedFilesCommand

logger = logging.getLogger(__name__)


class CleanupDeletedFilesMCPCommand(BaseMCPCommand):
    """
    Purge **file** trash: soft-deleted file rows (already moved under ``trash_dir``).

    This is not the same as ``delete_file`` (which **moves** into trash). With
    ``hard_delete=True``, permanently removes trashed file bytes and DB rows — i.e.
    **empty the recycle bin** for those files. Project-level trash uses ``clear_trash`` /
    ``permanently_delete_from_trash`` instead.
    """

    name = "cleanup_deleted_files"
    version = "1.0.0"
    descr = (
        "Purge soft-deleted **files**: list trashed file rows; with hard_delete=True, "
        "permanently remove bytes + DB (empty file recycle bin). Not for whole-project trash."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": (
                "Targets rows already soft-deleted (``delete_file`` / file watcher). "
                "``dry_run`` lists candidates; ``hard_delete=True`` performs **permanent** "
                "removal (disk under trash + DB) — the usual “empty trash” step for files. "
                "Project directories in ``trash_dir`` are handled by ``clear_trash`` / "
                "``permanently_delete_from_trash``, not this command."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID (from list_projects); if omitted, all projects",
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
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: Optional[str] = None,
        dry_run: bool = False,
        older_than_days: Optional[int] = None,
        hard_delete: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute cleanup deleted files command.

        Args:
            project_id: Optional project UUID (all projects if None).
            dry_run: If True, only show what would be deleted
            older_than_days: Only delete files deleted more than N days ago
            hard_delete: If True, permanently delete

        Returns:
            SuccessResult with cleanup statistics or ErrorResult on failure
        """
        try:
            if project_id:
                self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            try:
                command = CleanupDeletedFilesCommand(
                    database=database,
                    project_id=project_id,
                    dry_run=dry_run,
                    older_than_days=older_than_days,
                    hard_delete=hard_delete,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "CLEANUP_ERROR", "cleanup_deleted_files")

    @classmethod
    def metadata(cls: type["CleanupDeletedFilesMCPCommand"]) -> Dict[str, Any]:
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
                "The cleanup_deleted_files command cleans up deleted files from the database. "
                "It can perform soft delete (just listing) or hard delete (permanent removal). "
                "Hard delete permanently removes files and all related data from the database.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (if provided) or processes all projects\n"
                "4. Retrieves deleted files from database (where deleted=1)\n"
                "5. If older_than_days specified, filters files deleted more than N days ago\n"
                "6. If dry_run=True:\n"
                "   - Lists files that would be deleted\n"
                "   - Returns statistics without making changes\n"
                "7. If dry_run=False and hard_delete=False:\n"
                "   - Lists deleted files (soft delete - no actual deletion)\n"
                "8. If hard_delete=True:\n"
                "   - Permanently deletes file record from database\n"
                "   - Removes physical file from version directory\n"
                "   - Removes all chunks and removes from FAISS index\n"
                "   - Removes all classes, functions, methods\n"
                "   - Removes all AST trees\n"
                "   - Removes all vector indexes\n"
                "9. Returns cleanup statistics\n\n"
                "Delete Types:\n"
                "- Soft delete (hard_delete=False): Only lists deleted files, no actual deletion\n"
                "- Hard delete (hard_delete=True): Permanently removes file and all related data\n\n"
                "Use cases:\n"
                "- Clean up old deleted files\n"
                "- Free up database space\n"
                "- Remove files deleted more than N days ago\n"
                "- Permanently remove files (use with caution)\n\n"
                "Important notes:\n"
                "- Hard delete is PERMANENT and cannot be recovered\n"
                "- Always use dry_run=True first to see what would be deleted\n"
                "- older_than_days helps prevent accidental deletion of recently deleted files\n"
                "- If project_id is None, processes all projects\n"
                "- Hard delete removes all data: file, chunks, AST, vectors, entities"
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
                        "Optional project UUID. If omitted, processes all projects. "
                        "If provided, only cleans up files for that project."
                    ),
                    "type": "string",
                    "required": False,
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be deleted without actually deleting. "
                        "Default is False. Always use dry_run=True first to preview changes."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "older_than_days": {
                    "description": (
                        "Only delete files deleted more than N days ago. Optional. "
                        "Helps prevent accidental deletion of recently deleted files. "
                        "If not specified, processes all deleted files."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "hard_delete": {
                    "description": (
                        "If True, permanently deletes files and all related data. "
                        "Default is False (soft delete - just listing). "
                        "WARNING: Hard delete is PERMANENT and cannot be recovered. "
                        "Removes: file record, physical file, chunks, FAISS vectors, "
                        "classes, functions, methods, AST trees, vector indexes."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview what would be deleted (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Lists all deleted files that would be cleaned up without actually deleting. "
                        "Safe to run to preview changes."
                    ),
                },
                {
                    "description": "Clean up files deleted more than 30 days ago",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "older_than_days": 30,
                        "hard_delete": True,
                    },
                    "explanation": (
                        "Permanently deletes files that were deleted more than 30 days ago. "
                        "Useful for cleaning up old deleted files."
                    ),
                },
                {
                    "description": "Hard delete all deleted files for specific project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "hard_delete": True,
                    },
                    "explanation": (
                        "Permanently deletes all deleted files for the specified project. "
                        "WARNING: This is permanent and cannot be recovered."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "project_id='uuid' but project doesn't exist",
                    "solution": "Verify project_id is correct or omit to process all projects.",
                },
                "CLEANUP_ERROR": {
                    "description": "General error during cleanup",
                    "example": "Database error, file access error, or deletion failure",
                    "solution": (
                        "Check database integrity, verify file permissions, ensure files are accessible. "
                        "Use dry_run=True first to identify issues."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "deleted_files": (
                            "List of files that were deleted (or would be deleted). "
                            "Each entry contains file path and metadata."
                        ),
                        "total_files": "Total number of files processed",
                        "total_size": "Total size of deleted files (in bytes)",
                        "dry_run": "Whether this was a dry run",
                        "hard_delete": "Whether hard delete was performed",
                    },
                    "example": {
                        "deleted_files": [
                            {"path": "src/old_file.py", "size": 1024},
                        ],
                        "total_files": 1,
                        "total_size": 1024,
                        "dry_run": False,
                        "hard_delete": True,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, CLEANUP_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Always use dry_run=True first to preview what would be deleted",
                "Use older_than_days to prevent accidental deletion of recently deleted files",
                "Use hard_delete with caution - it's permanent and cannot be recovered",
                "Run this command periodically to clean up old deleted files",
                "Backup database before hard delete operations",
                "If project_id is None, processes all projects - be careful with hard_delete",
            ],
        }
