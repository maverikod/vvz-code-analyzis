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
            },
            "required": ["file_path"],
            "additionalProperties": False,
            "examples": [{"file_path": "/abs/path/to/file.py"}],
        }

    async def execute(
        self: "FormatCodeCommand", file_path: str, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        """Execute code formatting.

        Args:
            self: Command instance.
            file_path: Path to Python file to format.
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

            if success:
                return SuccessResult(
                    data={
                        "file_path": str(path),
                        "formatted": True,
                        "message": "Code formatted successfully",
                    }
                )

            return ErrorResult(
                code="FORMATTING_FAILED",
                message=error or "Formatting failed",
            )

        except Exception as e:
            logger.exception(f"Error formatting code: {e}")
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=f"Internal error: {str(e)}",
            )


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
