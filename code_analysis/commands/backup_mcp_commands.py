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
