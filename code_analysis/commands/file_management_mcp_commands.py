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
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path (current in version_dir or original_path)",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only show what would be restored",
                    "default": False,
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute unmark deleted file command.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            file_path: File path (current in version_dir or original_path)
            dry_run: If True, only show what would be restored

        Returns:
            SuccessResult with restoration information or ErrorResult on failure
        """
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            try:
                command = UnmarkDeletedFileCommand(
                    database=database,
                    file_path=file_path,
                    project_id=project_id,
                    dry_run=dry_run,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "UNMARK_ERROR", "unmark_deleted_file")

    @classmethod
    def metadata(cls: type["UnmarkDeletedFileMCPCommand"]) -> Dict[str, Any]:
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
                "The unmark_deleted_file command unmarks a file as deleted and restores it from "
                "the version directory back to its original location. This is a recovery operation "
                "that moves files back from the version directory to the project directory.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Searches for file in database by path or original_path\n"
                "5. Retrieves file record with original_path and version_dir\n"
                "6. If dry_run=True:\n"
                "   - Shows what would be restored without actually restoring\n"
                "7. If dry_run=False:\n"
                "   - Moves file from version_dir back to original_path\n"
                "   - Clears original_path and version_dir columns\n"
                "   - Sets deleted=0, updates updated_at\n"
                "   - File will be processed again by file watcher\n"
                "8. Returns restoration information\n\n"
                "Recovery Process:\n"
                "- File is moved from version directory to original location\n"
                "- Database record is updated (deleted=0)\n"
                "- File watcher will detect and process the restored file\n"
                "- All file data (AST, CST, chunks) is preserved\n\n"
                "Use cases:\n"
                "- Recover accidentally deleted files\n"
                "- Restore files from version directory\n"
                "- Undo file deletion\n\n"
                "Important notes:\n"
                "- File must have original_path in database (cannot restore if missing)\n"
                "- File must exist in version directory\n"
                "- Original location must be writable\n"
                "- Use dry_run=True to preview restoration"
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
                "file_path": {
                    "description": (
                        "File path to restore. Can be current path (in version_dir) or original_path. "
                        "Command searches for file by either path."
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
                "dry_run": {
                    "description": (
                        "If True, only shows what would be restored without actually restoring. "
                        "Default is False. Use to preview restoration."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview file restoration (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Shows what would be restored without actually restoring the file."
                    ),
                },
                {
                    "description": "Restore deleted file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Restores src/main.py from version directory back to original location."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "FILE_NOT_FOUND": {
                    "description": "File not found in database",
                    "example": "file_path='src/main.py' but file not in database",
                    "solution": "Verify file path is correct and file exists in database.",
                },
                "NO_ORIGINAL_PATH": {
                    "description": "File has no original_path, cannot restore",
                    "example": "File was deleted but original_path is missing",
                    "solution": (
                        "File cannot be restored without original_path. "
                        "Use repair_database to fix database integrity."
                    ),
                },
                "UNMARK_ERROR": {
                    "description": "General error during file restoration",
                    "example": "File move error, permission denied, or database error",
                    "solution": (
                        "Check file permissions, verify version directory exists, "
                        "ensure original location is writable."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "restored": "Whether file was restored (True) or would be restored (dry_run)",
                        "file_path": "File path that was processed",
                        "original_path": "Original path where file will be restored",
                        "version_dir": "Version directory where file currently is",
                        "dry_run": "Whether this was a dry run",
                        "message": "Status message",
                    },
                    "example": {
                        "restored": True,
                        "file_path": "src/main.py",
                        "original_path": "src/main.py",
                        "version_dir": "data/versions/.../src/main.py",
                        "dry_run": False,
                        "message": "Restored file to src/main.py",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FILE_NOT_FOUND, NO_ORIGINAL_PATH, UNMARK_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use dry_run=True first to preview restoration",
                "Verify file exists in version directory before restoring",
                "Ensure original location is writable",
                "File will be automatically processed by file watcher after restoration",
                "Use repair_database if original_path is missing",
            ],
        }


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
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
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
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        version_dir: str = "data/versions",
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute repair database command.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            version_dir: Version directory for deleted files (relative to project root)
            dry_run: If True, only show what would be repaired

        Returns:
            SuccessResult with repair statistics or ErrorResult on failure
        """
        try:
            from pathlib import Path

            root_path = self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            if not Path(version_dir).is_absolute():
                version_dir = str(root_path / version_dir)

            try:
                command = RepairDatabaseCommand(
                    database=database,
                    project_id=project_id,
                    root_dir=root_path,
                    version_dir=version_dir,
                    dry_run=dry_run,
                )
                result = await command.execute()
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "REPAIR_DATABASE_ERROR", "repair_database")

    @classmethod
    def metadata(cls: type["RepairDatabaseMCPCommand"]) -> Dict[str, Any]:
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
                "The repair_database command repairs database integrity by restoring correct file "
                "status based on actual file presence in the project directory and version directory. "
                "It synchronizes the database with the actual file system state.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Resolves version_dir path (relative to root_dir if not absolute)\n"
                "5. For each file in database:\n"
                "   - Checks if file exists in project directory\n"
                "   - Checks if file exists in version directory\n"
                "   - Updates database status accordingly\n"
                "6. Repair actions:\n"
                "   - If file exists in project directory: Remove deleted flag (deleted=0)\n"
                "   - If file exists in versions but not in project: Set deleted flag (deleted=1)\n"
                "   - If file doesn't exist anywhere: Restore from CST nodes:\n"
                "     * Place file in versions directory\n"
                "     * Add to project files if not marked for deletion\n"
                "7. If dry_run=True:\n"
                "   - Lists files that would be repaired\n"
                "   - Shows repair actions without making changes\n"
                "8. If dry_run=False:\n"
                "   - Performs actual repairs\n"
                "   - Updates database records\n"
                "   - Restores files from CST if needed\n"
                "9. Returns repair statistics\n\n"
                "Repair Actions:\n"
                "- Restore deleted flag: Files in project directory should not be marked deleted\n"
                "- Set deleted flag: Files in versions but not in project should be marked deleted\n"
                "- Restore from CST: Files missing from filesystem can be restored from CST nodes\n\n"
                "Use cases:\n"
                "- Fix database inconsistencies after manual file operations\n"
                "- Restore correct file status after file system changes\n"
                "- Recover files from CST nodes\n"
                "- Synchronize database with file system state\n\n"
                "Important notes:\n"
                "- Always use dry_run=True first to preview repairs\n"
                "- Restores files from CST nodes if they don't exist in filesystem\n"
                "- Updates database to match actual file system state\n"
                "- version_dir defaults to 'data/versions' if not specified"
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
                "version_dir": {
                    "description": (
                        "Version directory for deleted files. Default is 'data/versions'. "
                        "If relative, resolved relative to root_dir. "
                        "This is where deleted files are stored."
                    ),
                    "type": "string",
                    "required": False,
                    "default": "data/versions",
                },
                "dry_run": {
                    "description": (
                        "If True, only shows what would be repaired without actually repairing. "
                        "Default is False. Always use dry_run=True first to preview changes."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview database repairs (dry run)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "dry_run": True,
                    },
                    "explanation": (
                        "Lists all files that would be repaired, showing repair actions "
                        "without actually making changes."
                    ),
                },
                {
                    "description": "Repair database integrity",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Repairs database integrity by synchronizing file status with actual file system. "
                        "Restores files from CST if needed."
                    ),
                },
                {
                    "description": "Repair with custom version directory",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "version_dir": "custom/versions",
                    },
                    "explanation": (
                        "Repairs database using custom version directory for deleted files."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "REPAIR_DATABASE_ERROR": {
                    "description": "General error during database repair",
                    "example": "Database error, file access error, or CST restoration failure",
                    "solution": (
                        "Check database integrity, verify file permissions, ensure version directory exists. "
                        "Use dry_run=True first to identify issues."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "repaired_files": (
                            "List of files that were repaired. Each entry contains:\n"
                            "- path: File path\n"
                            "- action: Repair action (restore_deleted_flag, set_deleted_flag, restore_from_cst)\n"
                            "- status: File status after repair"
                        ),
                        "total_repaired": "Total number of files repaired",
                        "dry_run": "Whether this was a dry run",
                        "message": "Status message",
                    },
                    "example": {
                        "repaired_files": [
                            {
                                "path": "src/main.py",
                                "action": "restore_deleted_flag",
                                "status": "active",
                            },
                        ],
                        "total_repaired": 1,
                        "dry_run": False,
                        "message": "Repaired 1 files",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, REPAIR_DATABASE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Always use dry_run=True first to preview what would be repaired",
                "Run this command after manual file system operations",
                "Use to fix database inconsistencies",
                "Files can be restored from CST nodes if missing from filesystem",
                "Regular repairs help maintain database integrity",
            ],
        }
