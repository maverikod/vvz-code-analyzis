"""
Format code MCP command (Black).

Provides MCP interface for Black formatter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from ..core.code_quality import format_code_with_black

logger = logging.getLogger(__name__)


class FormatCodeCommand(Command):
    """Format Python code using Black.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "format_code"
    version = "1.0.0"
    descr = "Format Python code using black formatter"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["FormatCodeCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Format a Python file using Black.",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (relative to project root if project_id given, else absolute).",
                    "examples": ["/abs/path/to/file.py", "hello_cli.py"],
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID. If provided, file_path is relative to project root and DB is updated after format.",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
            "examples": [
                {"file_path": "/abs/path/to/file.py"},
                {
                    "file_path": "hello_cli.py",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                },
            ],
        }

    async def execute(
        self: "FormatCodeCommand",
        file_path: str,
        project_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute code formatting.

        Args:
            self: Command instance.
            file_path: Path to Python file (relative to project root if project_id given).
            project_id: Optional project UUID. If provided, DB is updated after format.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with formatting result or ErrorResult on failure.
        """
        try:
            if project_id:
                root_path = BaseMCPCommand._resolve_project_root(project_id)
                path = (root_path / file_path).resolve()
                backup_root = root_path
            else:
                path = Path(file_path).resolve()
                backup_root = path.parent
            if not path.exists():
                return ErrorResult(
                    code="FILE_NOT_FOUND",
                    message=f"File not found: {file_path}",
                )

            if not path.is_file():
                return ErrorResult(
                    code="NOT_A_FILE",
                    message=f"Path is not a file: {file_path}",
                )

            backup_mgr = BackupManager(backup_root)
            backup_uuid = backup_mgr.create_backup(
                path,
                command="format_code",
                comment="Before format",
            )
            if not backup_uuid:
                logger.warning("Failed to create backup before format_code")

            success, error = format_code_with_black(path)

            if not success:
                return ErrorResult(
                    code="FORMATTING_FAILED",
                    message=error or "Formatting failed",
                )

            database_updated = False
            if project_id:
                try:
                    import os

                    database = BaseMCPCommand._open_database_from_config(
                        auto_analyze=False
                    )
                    try:
                        file_stat = os.stat(path)
                        last_modified = file_stat.st_mtime
                        files = database.select(
                            "files",
                            where={"path": str(path), "project_id": project_id},
                        )
                        if files:
                            file_id = files[0]["id"]
                            database.update(
                                "files",
                                where={"id": file_id},
                                data={"last_modified": last_modified},
                            )
                            database_updated = True
                            logger.debug(
                                f"Database updated after formatting: {file_path} | last_modified={last_modified}"
                            )
                        else:
                            logger.debug(
                                f"File not found in database: {file_path}, skipping update"
                            )
                    finally:
                        database.disconnect()
                except Exception as e:
                    logger.warning(
                        f"Error updating database after formatting: {e}", exc_info=True
                    )

            return SuccessResult(
                data={
                    "file_path": str(path),
                    "formatted": True,
                    "database_updated": database_updated,
                    "message": "Code formatted successfully",
                }
            )

        except Exception as e:
            logger.exception(f"Error formatting code: {e}")
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=f"Internal error: {str(e)}",
            )

    @classmethod
    def metadata(cls: type["FormatCodeCommand"]) -> Dict[str, Any]:
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
                "The format_code command formats Python code using Black, the uncompromising "
                "code formatter. It automatically reformats code to follow Black's style guide, "
                "which enforces consistent formatting across the codebase.\n\n"
                "Operation flow:\n"
                "1. Validates file_path exists and is a file\n"
                "2. Reads file content from disk\n"
                "3. Attempts to format using Black library API (format_str)\n"
                "4. If Black library not available, falls back to subprocess execution\n"
                "5. Compares formatted content with original\n"
                "6. If content changed, writes formatted content back to file\n"
                "7. Returns success status\n\n"
                "Formatting Behavior:\n"
                "- Black enforces consistent code style (line length, quotes, spacing, etc.)\n"
                "- Default line length is 88 characters\n"
                "- Code is reformatted in-place (file is modified)\n"
                "- If file is already formatted, no changes are made\n"
                "- Black is opinionated and makes minimal formatting decisions\n\n"
                "Black Features:\n"
                "- Automatic code formatting\n"
                "- Consistent style across codebase\n"
                "- Handles string quotes, line breaks, indentation\n"
                "- Preserves code semantics (only formatting changes)\n"
                "- Fast and reliable formatting\n\n"
                "Use cases:\n"
                "- Format code before committing\n"
                "- Ensure consistent code style\n"
                "- Automate code formatting in workflows\n"
                "- Fix formatting issues after manual edits\n"
                "- Prepare code for code review\n\n"
                "Important notes:\n"
                "- File is modified in-place (original formatting is lost)\n"
                "- Black is opinionated - it makes formatting decisions automatically\n"
                "- If file is already formatted, operation succeeds with no changes\n"
                "- Requires Black to be installed (as library or CLI tool)\n"
                "- Falls back to subprocess if library API unavailable"
            ),
            "parameters": {
                "file_path": {
                    "description": (
                        "Path to Python file to format. "
                        "**RECOMMENDED: Use absolute path for reliability.** "
                        "Relative paths are resolved from current working directory, "
                        "which may cause issues if working directory changes. "
                        "File must exist and be readable/writable."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project/src/main.py",
                        "code_analysis/core/backup_manager.py",
                        "./src/utils.py",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Format a Python file",
                    "command": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                    },
                    "explanation": (
                        "Formats main.py using Black. File is modified in-place if formatting changes are needed."
                    ),
                },
                {
                    "description": "Format file in current directory",
                    "command": {
                        "file_path": "./code_analysis/commands/backup_mcp_commands.py",
                    },
                    "explanation": (
                        "Formats backup_mcp_commands.py. Relative paths are resolved from current working directory."
                    ),
                },
            ],
            "error_cases": {
                "FILE_NOT_FOUND": {
                    "description": "File does not exist",
                    "example": "file_path='/path/to/nonexistent.py'",
                    "solution": "Verify file path is correct and file exists",
                },
                "NOT_A_FILE": {
                    "description": "Path is not a file (e.g., directory)",
                    "example": "file_path='/path/to/directory'",
                    "solution": "Ensure path points to a file, not a directory",
                },
                "FORMATTING_FAILED": {
                    "description": "Black formatting failed",
                    "examples": [
                        {
                            "case": "Syntax errors in code",
                            "message": "Black formatting error: invalid syntax",
                            "solution": "Fix syntax errors before formatting",
                        },
                        {
                            "case": "Black not installed",
                            "message": "Black formatter not installed",
                            "solution": "Install Black: pip install black",
                        },
                        {
                            "case": "Timeout",
                            "message": "Formatting timed out",
                            "solution": "Check file size, ensure Black is working correctly",
                        },
                    ],
                },
                "INTERNAL_ERROR": {
                    "description": "Internal error during formatting",
                    "example": "Unexpected exception in formatting logic",
                    "solution": "Check logs for details, verify file permissions",
                },
            },
            "return_value": {
                "success": {
                    "description": "Code formatted successfully",
                    "data": {
                        "file_path": "Path to formatted file",
                        "formatted": "Always True on success",
                        "message": "Human-readable success message",
                    },
                    "example": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "formatted": True,
                        "message": "Code formatted successfully",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., FILE_NOT_FOUND, NOT_A_FILE, FORMATTING_FAILED, INTERNAL_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run format_code before committing code to ensure consistent style",
                "Use format_code after manual code edits to fix formatting",
                "Format code before running lint_code to avoid style-related lint errors",
                "If formatting fails, check for syntax errors first",
                "Black is opinionated - accept its formatting decisions",
                "Consider using format_code in pre-commit hooks",
                "Format code regularly to maintain consistency",
            ],
        }
