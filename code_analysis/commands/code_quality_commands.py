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
    """
    Command for formatting Python code using black.
    """

    name = "format_code"
    version = "1.0.0"
    descr = "Format Python code using black formatter"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file to format",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, file_path: str, **kwargs) -> SuccessResult | ErrorResult:
        """
        Execute code formatting.

        Args:
            file_path: Path to Python file to format

        Returns:
            SuccessResult with formatting result or ErrorResult on failure
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
            else:
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
    """
    Command for linting Python code using flake8.
    """

    name = "lint_code"
    version = "1.0.0"
    descr = "Lint Python code using flake8"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file to lint",
                },
                "ignore": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of error codes to ignore",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self, file_path: str, ignore: Optional[List[str]] = None, **kwargs
    ) -> SuccessResult | ErrorResult:
        """
        Execute code linting.

        Args:
            file_path: Path to Python file to lint
            ignore: Optional list of error codes to ignore

        Returns:
            SuccessResult with linting result or ErrorResult on failure
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
    """
    Command for type checking Python code using mypy.
    """

    name = "type_check_code"
    version = "1.0.0"
    descr = "Type check Python code using mypy"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file to type check",
                },
                "config_file": {
                    "type": "string",
                    "description": "Optional path to mypy config file",
                },
                "ignore_errors": {
                    "type": "boolean",
                    "description": "If True, treat errors as warnings",
                    "default": False,
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        config_file: Optional[str] = None,
        ignore_errors: bool = False,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute type checking.

        Args:
            file_path: Path to Python file to type check
            config_file: Optional path to mypy config file
            ignore_errors: If True, treat errors as warnings

        Returns:
            SuccessResult with type checking result or ErrorResult on failure
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
            if config_file and not config_path.exists():
                return ErrorResult(
                    code="CONFIG_NOT_FOUND",
                    message=f"Config file not found: {config_file}",
                )

            success, error, errors = type_check_with_mypy(
                path, config_file=config_path, ignore_errors=ignore_errors
            )

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
            logger.exception(f"Error type checking code: {e}")
            return ErrorResult(
                code="INTERNAL_ERROR",
                message=f"Internal error: {str(e)}",
            )
