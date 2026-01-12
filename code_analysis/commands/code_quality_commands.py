"""
Code quality MCP commands.

Provides MCP interface for black, flake8, and mypy tools.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..core.code_quality import (
    format_code_with_black,
    lint_with_flake8,
    type_check_with_mypy,
)

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
                    "description": "Path to Python file to format.",
                    "examples": ["/abs/path/to/file.py"],
                },
                "root_dir": {
                    "type": "string",
                    "description": "Optional project root directory. If provided, database will be updated after formatting.",
                    "examples": ["/abs/path/to/project"],
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
            "examples": [
                {"file_path": "/abs/path/to/file.py"},
                {
                    "file_path": "/abs/path/to/file.py",
                    "root_dir": "/abs/path/to/project",
                },
            ],
        }

    async def execute(
        self: "FormatCodeCommand",
        file_path: str,
        root_dir: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute code formatting.

        Args:
            self: Command instance.
            file_path: Path to Python file to format.
            root_dir: Optional project root directory. If provided, database will be updated after formatting.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with formatting result or ErrorResult on failure.
        """
        try:
            path = Path(file_path)
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

            success, error = format_code_with_black(path)

            if not success:
                return ErrorResult(
                    code="FORMATTING_FAILED",
                    message=error or "Formatting failed",
                )

            # Optional: Update database if root_dir is provided
            database_updated = False
            if root_dir:
                try:
                    from ..core.database import CodeDatabase
                    from ..core.project_resolution import get_project_id
                    from ..core.storage_paths import resolve_storage_paths
                    from pathlib import Path as PathType

                    root_path = PathType(root_dir)
                    if not root_path.exists() or not root_path.is_dir():
                        logger.warning(
                            f"Invalid root_dir: {root_dir}, skipping database update"
                        )
                    else:
                        # Open database
                        storage_paths = resolve_storage_paths(root_path)
                        db_path = storage_paths["database"]
                        from ..core.database.base import create_driver_config_for_worker

                        driver_config = create_driver_config_for_worker(db_path)
                        database = CodeDatabase(driver_config=driver_config)

                        # Get project_id
                        project_id = get_project_id(root_path)
                        if project_id:
                            # Update database after formatting
                            # Note: Formatting doesn't change code structure, only formatting
                            # But we update to reflect new file_mtime
                            update_result = database.update_file_data(
                                file_path=str(path),
                                project_id=project_id,
                                root_dir=root_path,
                            )
                            if update_result.get("success"):
                                database_updated = True
                                logger.debug(
                                    f"Database updated after formatting: {file_path} | "
                                    f"AST={update_result.get('ast_updated')}, "
                                    f"CST={update_result.get('cst_updated')}"
                                )
                            else:
                                logger.warning(
                                    f"Failed to update database after formatting: {file_path} | "
                                    f"Error: {update_result.get('error')}"
                                )
                        else:
                            logger.debug(
                                f"Project ID not found for {root_dir}, skipping database update"
                            )
                except Exception as e:
                    # Don't fail formatting if database update fails
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
                        "/home/user/projects/my_project/src/main.py",  # ✅ RECOMMENDED: Absolute path
                        "code_analysis/core/backup_manager.py",  # ⚠️ Relative path (resolved from CWD)
                        "./src/utils.py",  # ⚠️ Relative path (resolved from CWD)
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
                    "description": "Path to Python file to lint.",
                    "examples": ["/abs/path/to/file.py"],
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
                {"file_path": "/abs/path/to/file.py", "ignore": ["E501"]},
            ],
        }

    async def execute(
        self: "LintCodeCommand",
        file_path: str,
        ignore: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute code linting.

        Args:
            self: Command instance.
            file_path: Path to Python file to lint.
            ignore: Optional list of error codes to ignore.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with linting result or ErrorResult on failure.
        """
        try:
            path = Path(file_path)
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
                        "Path to Python file to lint. "
                        "**RECOMMENDED: Use absolute path for reliability.** "
                        "Relative paths are resolved from current working directory, "
                        "which may cause issues if working directory changes. "
                        "File must exist and be readable."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project/src/main.py",  # ✅ RECOMMENDED: Absolute path
                        "code_analysis/core/backup_manager.py",  # ⚠️ Relative path (resolved from CWD)
                        "./src/utils.py",  # ⚠️ Relative path (resolved from CWD)
                    ],
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


class TypeCheckCodeCommand(Command):
    """Type check Python code using mypy.

    Notes:
        If `config_file` is not provided, this command tries to auto-detect
        `pyproject.toml` in parent directories of `file_path`.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "type_check_code"
    version = "1.0.0"
    descr = "Type check Python code using mypy"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["TypeCheckCodeCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": "Type check Python code using mypy.",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file to type check.",
                    "examples": ["/abs/path/to/file.py"],
                },
                "config_file": {
                    "type": "string",
                    "description": "Optional path to mypy config file (e.g. pyproject.toml).",
                    "examples": ["/abs/path/to/pyproject.toml"],
                },
                "ignore_errors": {
                    "type": "boolean",
                    "description": "If True, treat errors as warnings.",
                    "default": False,
                    "examples": [False],
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
            "examples": [
                {"file_path": "/abs/path/to/file.py"},
                {
                    "file_path": "/abs/path/to/file.py",
                    "config_file": "/abs/path/to/pyproject.toml",
                    "ignore_errors": False,
                },
            ],
        }

    async def execute(
        self: "TypeCheckCodeCommand",
        file_path: str,
        config_file: Optional[str] = None,
        ignore_errors: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute type checking.

        Args:
            self: Command instance.
            file_path: Path to Python file to type check.
            config_file: Optional path to mypy config file. If omitted, the command
                tries to auto-detect `pyproject.toml` in parent directories.
            ignore_errors: If True, treat errors as warnings.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with type checking result or ErrorResult on failure.
        """
        try:
            path = Path(file_path)
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

            config_path = Path(config_file) if config_file else None
            if config_file and config_path and not config_path.exists():
                return ErrorResult(
                    code="CONFIG_NOT_FOUND",
                    message=f"Config file not found: {config_file}",
                )

            if config_path is None:
                for parent in [path.parent, *path.parent.parents]:
                    candidate = parent / "pyproject.toml"
                    if candidate.exists() and candidate.is_file():
                        config_path = candidate
                        break

            success, error, errors = type_check_with_mypy(
                path, config_file=config_path, ignore_errors=ignore_errors
            )

            return SuccessResult(
                data={
                    "file_path": str(path),
                    "config_file": str(config_path) if config_path else None,
                    "success": success,
                    "error": error,
                    "errors": errors,
                    "error_count": len(errors),
                }
            )

        except Exception as e:
            logger.exception(f"Error type checking code: {e}")
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=f"Internal error: {str(e)}",
            )

    @classmethod
    def metadata(cls: type["TypeCheckCodeCommand"]) -> Dict[str, Any]:
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
                "The type_check_code command performs static type checking on Python code "
                "using mypy. It analyzes type annotations and detects type errors, "
                "missing type hints, and type inconsistencies without running the code.\n\n"
                "Operation flow:\n"
                "1. Validates file_path exists and is a file\n"
                "2. If config_file provided, validates it exists\n"
                "3. If config_file not provided, auto-detects pyproject.toml in parent directories\n"
                "4. If config points to this repository, runs mypy on entire package\n"
                "5. Otherwise, runs mypy on single file\n"
                "6. Executes mypy via subprocess with sanitized PYTHONPATH\n"
                "7. Collects type errors from stdout and stderr\n"
                "8. Returns success status and list of errors\n\n"
                "Type Checking Behavior:\n"
                "- Analyzes type annotations (function parameters, return types, variables)\n"
                "- Detects type mismatches and inconsistencies\n"
                "- Checks for missing type hints\n"
                "- Validates generic types and type aliases\n"
                "- Respects mypy configuration from config_file\n"
                "- File is not modified (read-only analysis)\n\n"
                "Config File Detection:\n"
                "- If config_file not provided, searches for pyproject.toml in:\n"
                "  1. File's parent directory\n"
                "  2. Parent's parent directory (and up)\n"
                "- Stops at first found pyproject.toml\n"
                "- If config points to this repository, runs package-level check\n"
                "- Otherwise, runs file-level check\n\n"
                "Package vs File Mode:\n"
                "- Package mode: Runs 'mypy -p code_analysis' (checks entire package)\n"
                "  - Avoids duplicate module discovery issues\n"
                "  - Better relative import resolution\n"
                "  - More comprehensive type checking\n"
                "- File mode: Runs 'mypy file.py' (checks single file)\n"
                "  - Faster for single file checks\n"
                "  - May have issues with relative imports\n\n"
                "Use cases:\n"
                "- Validate type annotations before committing\n"
                "- Find type errors without running code\n"
                "- Ensure type safety across codebase\n"
                "- Check type hints completeness\n"
                "- Validate generic types and type aliases\n"
                "- Enforce type checking in CI/CD pipelines\n\n"
                "Important notes:\n"
                "- File is not modified (type checking is read-only)\n"
                "- Requires mypy to be installed\n"
                "- PYTHONPATH is sanitized to avoid import conflicts\n"
                "- Package mode is used when config points to this repository\n"
                "- ignore_errors=True treats errors as warnings (still returns errors list)\n"
                "- success=True means no type errors found\n"
                "- success=False means type errors were found (check errors list)"
            ),
            "parameters": {
                "file_path": {
                    "description": (
                        "Path to Python file to type check. "
                        "**RECOMMENDED: Use absolute path for reliability.** "
                        "Relative paths are resolved from current working directory, "
                        "which may cause issues if working directory changes. "
                        "File must exist and be readable."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project/src/main.py",  # ✅ RECOMMENDED: Absolute path
                        "code_analysis/core/backup_manager.py",  # ⚠️ Relative path (resolved from CWD)
                        "./src/utils.py",  # ⚠️ Relative path (resolved from CWD)
                    ],
                },
                "config_file": {
                    "description": (
                        "Optional path to mypy configuration file (typically pyproject.toml). "
                        "If not provided, command auto-detects pyproject.toml in parent directories. "
                        "If config points to this repository, runs package-level type checking."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "/home/user/projects/my_project/pyproject.toml",
                        "./pyproject.toml",
                    ],
                },
                "ignore_errors": {
                    "description": (
                        "If True, treats type errors as warnings. Errors are still returned "
                        "in the errors list, but success will be True. Useful for gradual "
                        "type checking adoption or non-blocking checks."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [False, True],
                },
            },
            "usage_examples": [
                {
                    "description": "Type check a Python file",
                    "command": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                    },
                    "explanation": (
                        "Type checks main.py using auto-detected mypy config. "
                        "Returns all type errors found."
                    ),
                },
                {
                    "description": "Type check with explicit config",
                    "command": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "config_file": "/home/user/projects/my_project/pyproject.toml",
                    },
                    "explanation": (
                        "Type checks main.py using specified mypy config file. "
                        "If config points to this repo, runs package-level check."
                    ),
                },
                {
                    "description": "Type check with errors as warnings",
                    "command": {
                        "file_path": "./code_analysis/commands/backup_mcp_commands.py",
                        "ignore_errors": True,
                    },
                    "explanation": (
                        "Type checks file but treats errors as warnings. "
                        "Returns success=True even if errors found (errors still in list)."
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
                "CONFIG_NOT_FOUND": {
                    "description": "Config file specified but not found",
                    "example": "config_file='/path/to/missing/pyproject.toml'",
                    "solution": "Verify config file path is correct and file exists",
                },
                "INTERNAL_ERROR": {
                    "description": "Internal error during type checking",
                    "example": "Unexpected exception in type checking logic",
                    "solution": "Check logs for details, verify file permissions and mypy installation",
                },
            },
            "return_value": {
                "success": {
                    "description": "Type checking completed (may have errors)",
                    "data": {
                        "file_path": "Path to type-checked file",
                        "config_file": "Path to mypy config file used (None if auto-detected or not found)",
                        "success": (
                            "True if no type errors found (or ignore_errors=True), "
                            "False if type errors found and ignore_errors=False"
                        ),
                        "error": "Error message if type checking failed (None if successful)",
                        "errors": (
                            "List of type error strings. Each error follows format: "
                            "file_path:line:column: error_type: error_message"
                        ),
                        "error_count": "Number of type errors found",
                    },
                    "example_success": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "config_file": "/home/user/projects/my_project/pyproject.toml",
                        "success": True,
                        "error": None,
                        "errors": [],
                        "error_count": 0,
                    },
                    "example_with_errors": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "config_file": "/home/user/projects/my_project/pyproject.toml",
                        "success": False,
                        "error": "Found 2 mypy errors",
                        "errors": [
                            "src/main.py:15:5: error: Argument 1 to 'process' has incompatible type 'str'; expected 'int'",
                            "src/main.py:22:10: error: Function is missing a return type annotation",
                        ],
                        "error_count": 2,
                    },
                    "example_ignore_errors": {
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "config_file": None,
                        "success": True,
                        "error": None,
                        "errors": [
                            "src/main.py:15:5: error: Argument 1 to 'process' has incompatible type 'str'; expected 'int'",
                        ],
                        "error_count": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., FILE_NOT_FOUND, NOT_A_FILE, CONFIG_NOT_FOUND, INTERNAL_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run type_check_code after adding type hints to validate them",
                "Fix all type errors before committing code",
                "Use ignore_errors=True for gradual type checking adoption",
                "Check error_count field to quickly see if issues exist",
                "Review errors list to understand type issues",
                "Run type_check_code in CI/CD pipelines to enforce type safety",
                "Use config_file for project-specific mypy settings",
                "Package mode (when config points to repo) provides better type checking",
                "Add type hints incrementally and check as you go",
                "Use mypy's strict mode for maximum type safety",
            ],
        }
