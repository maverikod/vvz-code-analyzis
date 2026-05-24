"""
Lint code MCP command (Flake8).

Provides MCP interface for Flake8 linter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.code_quality import lint_with_flake8
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class LintCodeCommand(Command):
    """Lint Python code using Flake8.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "lint_code"
    version = "1.0.0"
    descr = "Lint Python code using flake8"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["LintCodeCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Lint a Python file using Flake8.",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to Python file to lint. If project_id is provided, relative to project root."
                    ),
                    "examples": ["hello_cli.py", "/abs/path/to/file.py"],
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID. If provided, file_path is relative to project root.",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "ignore": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of flake8 error codes to ignore.",
                    "examples": [["E501", "W503"]],
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
                {
                    "file_path": "hello_cli.py",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "ignore": ["E501"],
                },
            ],
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters against command schema before queue or execute."""
        BaseMCPCommand.validate_params_against_schema(
            params, self.get_schema(), command_name=self.name
        )
        return params

    async def execute(
        self: "LintCodeCommand",
        file_path: str,
        project_id: Optional[str] = None,
        ignore: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute code linting.

        Args:
            self: Command instance.
            file_path: Path to Python file to lint (relative to project root if project_id given).
            project_id: Optional project UUID; file_path is resolved relative to project root.
            ignore: Optional list of error codes to ignore.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with linting result or ErrorResult on failure.
        """
        params: Dict[str, Any] = {
            "file_path": file_path,
            "project_id": project_id,
            "ignore": ignore,
        }
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        file_path = str(params["file_path"])
        project_id = params.get("project_id")
        ignore = params.get("ignore")
        try:
            if project_id:
                root_path = BaseMCPCommand._resolve_project_root(project_id)
                path = (root_path / file_path).resolve()
            else:
                path = Path(file_path).resolve()
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

            success, error, errors = lint_with_flake8(path, ignore=ignore)

            return SuccessResult(
                data={
                    "file_path": str(path),
                    "success": success,
                    "error": error,
                    "errors": errors,
                    "error_count": len(errors),
                }
            )

        except Exception as e:
            logger.exception(f"Error linting code: {e}")
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=f"Internal error: {str(e)}",
            )

    @classmethod
    def metadata(cls: type["LintCodeCommand"]) -> Dict[str, Any]:
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
                "The lint_code command lints Python code using Flake8, a tool that checks "
                "code style, programming errors, and complexity. It identifies issues like "
                "unused imports, undefined variables, style violations, and more.\n\n"
                "Operation flow:\n"
                "1. Validates file_path exists and is a file\n"
                "2. Attempts to lint using Flake8 library API\n"
                "3. If Flake8 library not available or fails, falls back to subprocess\n"
                "4. Collects all linting errors and warnings\n"
                "5. Returns success status and list of errors\n\n"
                "Linting Behavior:\n"
                "- Checks code style (PEP 8 compliance)\n"
                "- Detects programming errors (undefined names, unused imports, etc.)\n"
                "- Checks code complexity\n"
                "- Default max line length is 88 characters\n"
                "- Can ignore specific error codes via ignore parameter\n"
                "- File is not modified (read-only analysis)\n\n"
                "Flake8 Error Categories:\n"
                "- E: PEP 8 errors (indentation, whitespace, etc.)\n"
                "- W: PEP 8 warnings (line length, etc.)\n"
                "- F: Pyflakes errors (undefined names, unused imports, etc.)\n"
                "- C: McCabe complexity warnings\n"
                "- N: Naming convention violations\n\n"
                "Use cases:\n"
                "- Check code quality before committing\n"
                "- Find programming errors (undefined variables, unused imports)\n"
                "- Enforce code style standards\n"
                "- Identify code complexity issues\n"
                "- Validate code in CI/CD pipelines\n\n"
                "Important notes:\n"
                "- File is not modified (linting is read-only)\n"
                "- Returns list of all errors found\n"
                "- success=True means no errors found\n"
                "- success=False means errors were found (check errors list)\n"
                "- Can ignore specific error codes if needed\n"
                "- Requires Flake8 to be installed\n"
                "- PYTHONPATH is sanitized to avoid import conflicts"
            ),
            "parameters": {
                "file_path": {
                    "description": (
                        "Path to Python file to lint. If root_dir is provided, interpreted "
                        "relative to project root (e.g. 'hello_cli.py' -> root_dir/hello_cli.py). "
                        "Otherwise absolute path or relative to current working directory."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "hello_cli.py",
                        "/home/user/projects/my_project/src/main.py",
                    ],
                },
                "root_dir": {
                    "description": (
                        "Optional project root directory. When provided, file_path is resolved "
                        "relative to this directory."
                    ),
                    "type": "string",
                    "required": False,
                },
                "ignore": {
                    "description": (
                        "Optional list of Flake8 error codes to ignore. "
                        "Common codes: E501 (line too long), W503 (line break before binary operator), "
                        "F401 (imported but unused). See Flake8 documentation for full list."
                    ),
                    "type": "array",
                    "items": {"type": "string"},
                    "required": False,
                    "examples": [
                        ["E501"],
                        ["E501", "W503"],
                        ["F401", "F811"],
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Lint a Python file",
                    "command": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                    },
                    "explanation": (
                        "Lints main.py and returns all errors found. "
                        "Check success field and errors list in response."
                    ),
                },
                {
                    "description": "Lint with ignored error codes",
                    "command": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "ignore": ["E501", "W503"],
                    },
                    "explanation": (
                        "Lints main.py but ignores line length (E501) and "
                        "line break before operator (W503) errors."
                    ),
                },
                {
                    "description": "Check code quality before commit",
                    "command": {
                        "file_path": "./code_analysis/commands/backup_mcp_commands.py",
                    },
                    "explanation": (
                        "Lints backup_mcp_commands.py to find any code quality issues "
                        "before committing changes."
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
                "INTERNAL_ERROR": {
                    "description": "Internal error during linting",
                    "example": "Unexpected exception in linting logic",
                    "solution": "Check logs for details, verify file permissions",
                },
            },
            "return_value": {
                "success": {
                    "description": "Linting completed (may have errors)",
                    "data": {
                        "file_path": "Path to linted file",
                        "success": "True if no errors found, False if errors found",
                        "error": "Error message if linting failed (None if successful)",
                        "errors": (
                            "List of error strings. Each error follows format: "
                            "file_path:line:column: error_code error_message"
                        ),
                        "error_count": "Number of errors found",
                    },
                    "example_success": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "success": True,
                        "error": None,
                        "errors": [],
                        "error_count": 0,
                    },
                    "example_with_errors": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "success": False,
                        "error": "Found 3 flake8 errors",
                        "errors": [
                            "src/main.py:10:1: F401 'os' imported but unused",
                            "src/main.py:25:80: E501 line too long (120 > 88 characters)",
                            "src/main.py:42:5: F841 local variable 'x' is assigned to but never used",
                        ],
                        "error_count": 3,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., FILE_NOT_FOUND, NOT_A_FILE, INTERNAL_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run lint_code after format_code to check for remaining issues",
                "Fix all errors before committing code",
                "Use ignore parameter sparingly - only for legitimate cases",
                "Check error_count field to quickly see if issues exist",
                "Review errors list to understand what needs fixing",
                "Run lint_code in CI/CD pipelines to enforce code quality",
                "Address F errors (Pyflakes) first - they indicate real bugs",
                "Use ignore for style preferences, not for hiding real issues",
            ],
        }
