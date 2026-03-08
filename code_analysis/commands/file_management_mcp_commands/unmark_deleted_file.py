"""
MCP command wrappers for file management operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management import UnmarkDeletedFileCommand

logger = logging.getLogger(__name__)


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
                if result.get("error") == "FILE_EXISTS_AT_TARGET":
                    return ErrorResult(
                        code="FILE_EXISTS_AT_TARGET",
                        message=result.get(
                            "message",
                            "File already exists at target. Delete or rename it before restoring.",
                        ),
                    )
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
                "FILE_EXISTS_AT_TARGET": {
                    "description": "Target path already exists in project; restore would overwrite",
                    "example": "original_path already has a file on disk",
                    "solution": "Delete or rename the existing file at the target path before restoring.",
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
