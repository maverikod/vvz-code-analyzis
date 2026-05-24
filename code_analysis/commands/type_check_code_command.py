"""
Type check code MCP command (mypy).

Provides MCP interface for mypy type checker. Always runs in single-file scope.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.code_quality import type_check_with_mypy
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class TypeCheckCodeCommand(Command):
    """Type check Python code using mypy.

    Notes:
        If `config_file` is not provided, this command tries to auto-detect
        `pyproject.toml` in parent directories of `file_path`.
        This command always runs mypy in single-file mode (one target file).

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
                    "description": (
                        "Path to Python file to type check. If project_id is provided, "
                        "relative to project root."
                    ),
                    "examples": ["hello_cli.py", "/abs/path/to/file.py"],
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID. If provided, file_path is relative to project root.",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
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
                    "file_path": "hello_cli.py",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                {
                    "file_path": "hello_cli.py",
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "ignore_errors": False,
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
        self: "TypeCheckCodeCommand",
        file_path: str,
        project_id: Optional[str] = None,
        config_file: Optional[str] = None,
        ignore_errors: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute type checking.

        Args:
            self: Command instance.
            file_path: Path to Python file to type check (relative to project root if project_id given).
            project_id: Optional project UUID; file_path is relative to project root.
            config_file: Optional path to mypy config file.
            ignore_errors: If True, treat errors as warnings.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with type checking result or ErrorResult on failure.
        """
        params: Dict[str, Any] = {
            "file_path": file_path,
            "project_id": project_id,
            "config_file": config_file,
            "ignore_errors": ignore_errors,
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
        config_file = params.get("config_file")
        ignore_errors = bool(params.get("ignore_errors", False))
        try:
            input_path = Path(file_path)
            if project_id:
                root_path = BaseMCPCommand._resolve_project_root(project_id)
                path = (
                    input_path.resolve()
                    if input_path.is_absolute()
                    else (root_path / input_path).resolve()
                )
            else:
                path = input_path.resolve()
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

            config_path = Path(config_file).resolve() if config_file else None
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

            # Enforce strict single-file type check scope.
            # Repository-root pyproject triggers package-wide mode in type checker;
            # in this command we always target exactly one resolved file.
            if config_path and (config_path.parent / "code_analysis").is_dir():
                logger.debug(
                    "Skipping repository-root mypy config for strict single-file run: %s",
                    config_path,
                )
                config_path = None

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
                "Static type checking with mypy. Validates file_path, optional config_file; "
                "auto-detects pyproject.toml in parent dirs. Always runs mypy on the single "
                "target file (never package-wide). Repo-root config is skipped. Read-only; "
                "returns success and list of errors. ignore_errors=True treats errors as warnings."
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
                        "/home/user/projects/my_project/src/main.py",
                        "code_analysis/core/backup_manager.py",
                        "./src/utils.py",
                    ],
                },
                "config_file": {
                    "description": (
                        "Optional path to mypy configuration file (typically pyproject.toml). "
                        "If not provided, command auto-detects pyproject.toml in parent directories. "
                        "Repo-root config is skipped so type check stays single-file."
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
                        "Returns all type errors found for that file only."
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
                        "Result is still for the single file only."
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
                "This command always checks a single file; result set is scoped to that file",
                "Add type hints incrementally and check as you go",
                "Use mypy's strict mode for maximum type safety",
            ],
        }
