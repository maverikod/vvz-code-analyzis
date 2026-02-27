"""
MCP command: file_structure

Returns top-level classes with first-level methods and optional top-level
functions, with line ranges and line counts. For refactoring and split decisions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import libcst as cst
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_module import list_file_structure

logger = logging.getLogger(__name__)


def _syntax_error_message(e: cst.ParserSyntaxError) -> str:
    """Build a short, user-friendly description of the parser error."""
    line = getattr(e, "raw_line", None)
    col = getattr(e, "raw_column", None)
    parts = []
    if line is not None:
        parts.append(f"line {line}")
    if col is not None:
        parts.append(f"column {col + 1}")
    loc = " at " + ", ".join(parts) if parts else ""
    # Prefer parser message (e.g. "expected one of ..."); fallback to first line of str(e)
    desc = getattr(e, "message", None) or ""
    if desc and desc.startswith("parser error: "):
        desc = desc.replace("parser error: ", "", 1).strip()
    if not desc:
        raw = str(e).strip()
        desc = raw.split("\n")[0] if raw else "invalid syntax"
    if len(desc) > 120:
        desc = desc[:117] + "..."
    return f"The file contains a syntax error{loc}. {desc}"


class FileStructureCommand(BaseMCPCommand):
    """Show classes and first-level methods (and optionally functions) with line counts."""

    name = "file_structure"
    version = "1.0.0"
    descr = (
        "List top-level classes and their first-level methods (and optionally "
        "top-level functions) with start_line, end_line, and line_count for each"
    )
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to Python file (relative to project root). "
                        "Must be a .py file."
                    ),
                },
                "include_functions": {
                    "type": "boolean",
                    "description": (
                        "If true, include top-level functions in the result. "
                        "If false, only classes and their methods are returned. "
                        "Default: true."
                    ),
                    "default": True,
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        include_functions: bool = True,
        **kwargs: Any,
    ) -> SuccessResult:
        try:
            root_path = self._resolve_project_root(project_id)
            target = root_path / file_path
            target = target.resolve()

            if target.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )

            if not target.exists():
                return ErrorResult(
                    message="Target file does not exist",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            try:
                source = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as e:
                logger.warning("file_structure: file is not valid UTF-8: %s", e)
                return ErrorResult(
                    message=(
                        "The file could not be read as UTF-8. "
                        "Please save the file with UTF-8 encoding and try again."
                    ),
                    code="FILE_STRUCTURE_ERROR",
                    details={
                        "file_path": file_path,
                        "error_type": "encoding",
                        "reason": str(e),
                    },
                )

            structure = list_file_structure(source, include_functions=include_functions)
            data: Dict[str, Any] = {
                "success": True,
                "file_path": file_path,
                "classes": structure["classes"],
                "functions": structure["functions"],
            }
            return SuccessResult(data=data)
        except cst.ParserSyntaxError as e:
            logger.warning("file_structure: syntax error in %s: %s", file_path, e)
            user_message = _syntax_error_message(e)
            raw_col = getattr(e, "raw_column", None)
            details = {
                "file_path": file_path,
                "error_type": "syntax",
                "line": getattr(e, "raw_line", None),
                "column": (raw_col + 1) if raw_col is not None else None,
                "parser_message": str(e).strip(),
            }
            return ErrorResult(
                message=user_message,
                code="FILE_STRUCTURE_SYNTAX_ERROR",
                details=details,
            )
        except SyntaxError as e:
            logger.warning("file_structure: syntax error in %s: %s", file_path, e)
            line = e.lineno if e.lineno else getattr(e, "raw_line", None)
            msg = (
                f"Syntax error at line {line}: {e.msg}"
                if line
                else f"Syntax error: {e.msg}"
            )
            return ErrorResult(
                message=msg,
                code="FILE_STRUCTURE_SYNTAX_ERROR",
                details={
                    "file_path": file_path,
                    "error_type": "syntax",
                    "line": line,
                    "offset": getattr(e, "offset", None),
                },
            )
        except Exception as e:
            logger.exception("file_structure failed: %s", e)
            return ErrorResult(
                message=f"Could not analyze file structure: {e}",
                code="FILE_STRUCTURE_ERROR",
                details={"file_path": file_path},
            )

    @classmethod
    def metadata(cls: type["FileStructureCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Returns:
            Dictionary with command metadata, including schema, examples,
            and error cases.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The file_structure command returns a hierarchical view of a Python file: "
                "top-level classes with their first-level methods, and optionally "
                "top-level functions. For each class, method, and function it returns "
                "start_line, end_line, and line_count (number of lines, inclusive). "
                "This supports refactoring decisions (split_class, extract_superclass, "
                "split_file_to_package) by showing which classes or methods are large.\n\n"
                "Operation flow:\n"
                "1. Resolves project root from project_id\n"
                "2. Resolves file_path (relative to project root)\n"
                "3. Validates file is .py and exists\n"
                "4. Reads and parses source with LibCST\n"
                "5. Walks module body: collects top-level FunctionDef and ClassDef\n"
                "6. For each class, collects direct method definitions (first level only)\n"
                "7. Computes line_count as end_line - start_line + 1 for each item\n"
                "8. Returns classes (with nested methods) and optionally functions\n\n"
                "Output structure:\n"
                "- classes: list of { name, start_line, end_line, line_count, methods: [...] }\n"
                "- methods: list of { name, start_line, end_line, line_count }\n"
                "- functions: list of { name, start_line, end_line, line_count } (if include_functions)\n\n"
                "Use cases:\n"
                "- Before split_class: see which class is large and how methods are distributed\n"
                "- Before extract_superclass: see which classes share large methods\n"
                "- Before split_file_to_package: see classes/functions and their sizes to assign to modules\n"
                "- General: quick overview of file layout and size per class/method"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID from create_project or list_projects. "
                        "Used to resolve project root for file_path."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    ],
                },
                "file_path": {
                    "description": (
                        "Path to the Python file relative to project root. "
                        "Must be a .py file. File must exist."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "src/core/task_queue.py",
                        "code_analysis/commands/refactor_mcp_commands.py",
                        "tests/test_foo.py",
                    ],
                },
                "include_functions": {
                    "description": (
                        "If true (default), top-level functions are included in the "
                        "'functions' list. If false, only classes and their methods "
                        "are returned (functions list will be empty)."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                    "examples": [True, False],
                },
            },
            "usage_examples": [
                {
                    "description": "Get full file structure (classes + methods + functions)",
                    "command": {
                        "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                        "file_path": "src/core/handlers.py",
                    },
                    "explanation": (
                        "Returns all classes with their methods and top-level functions "
                        "with line counts. Use to decide which class to split or which "
                        "module to extract."
                    ),
                },
                {
                    "description": "Get only classes and methods (no top-level functions)",
                    "command": {
                        "project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9",
                        "file_path": "src/core/handlers.py",
                        "include_functions": False,
                    },
                    "explanation": (
                        "Use when you care only about class layout and method sizes."
                    ),
                },
                {
                    "description": "Prepare config for split_file_to_package",
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "file_path": "core/task_queue.py",
                    },
                    "explanation": (
                        "Inspect classes and functions with line counts, then build "
                        "config.modules mapping for split_file_to_package."
                    ),
                },
            ],
            "error_cases": {
                "INVALID_FILE": {
                    "description": "File is not a Python file",
                    "message": "Target file must be a .py file",
                    "solution": "Ensure file_path points to a .py file",
                },
                "FILE_NOT_FOUND": {
                    "description": "File does not exist at resolved path",
                    "message": "Target file does not exist",
                    "solution": "Verify project_id and file_path; ensure file exists in project root",
                },
                "FILE_STRUCTURE_SYNTAX_ERROR": {
                    "description": "File contains Python syntax errors; parser could not read the file",
                    "message": "Human-readable message with line (and column), e.g. 'Syntax error at line 5, column 3: expected ...'",
                    "solution": "Fix the syntax error at the reported line/column. details.line and details.column (1-based) point to the error; details.parser_message has the full parser output.",
                    "details": "file_path, error_type='syntax', line, column (1-based), parser_message",
                },
                "FILE_STRUCTURE_ERROR": {
                    "description": "Other errors (e.g. file not readable as UTF-8, or internal error)",
                    "examples": [
                        {
                            "case": "File is not UTF-8",
                            "message": "The file could not be read as UTF-8. Please save the file with UTF-8 encoding and try again.",
                            "solution": "Save the file with UTF-8 encoding.",
                            "details": "error_type='encoding', reason=...",
                        },
                        {
                            "case": "Other failure",
                            "message": "Could not analyze file structure: <exception text>",
                            "solution": "Check file_path and file contents; retry or report if persistent.",
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Structure listed successfully",
                    "data": {
                        "success": "Always True on success",
                        "file_path": "Requested file path (relative to project root)",
                        "classes": (
                            "List of class objects. Each has: name, start_line, end_line, "
                            "line_count, methods (list of { name, start_line, end_line, line_count })."
                        ),
                        "functions": (
                            "List of top-level function objects. Each has: name, start_line, "
                            "end_line, line_count. Empty if include_functions=false."
                        ),
                    },
                    "example": {
                        "success": True,
                        "file_path": "src/core/handlers.py",
                        "classes": [
                            {
                                "name": "UserManager",
                                "start_line": 20,
                                "end_line": 150,
                                "line_count": 131,
                                "methods": [
                                    {
                                        "name": "__init__",
                                        "start_line": 21,
                                        "end_line": 30,
                                        "line_count": 10,
                                    },
                                    {
                                        "name": "authenticate",
                                        "start_line": 32,
                                        "end_line": 85,
                                        "line_count": 54,
                                    },
                                    {
                                        "name": "authorize",
                                        "start_line": 87,
                                        "end_line": 120,
                                        "line_count": 34,
                                    },
                                ],
                            },
                        ],
                        "functions": [
                            {
                                "name": "create_guest_user",
                                "start_line": 5,
                                "end_line": 18,
                                "line_count": 14,
                            },
                        ],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "INVALID_FILE | FILE_NOT_FOUND | FILE_STRUCTURE_SYNTAX_ERROR | FILE_STRUCTURE_ERROR",
                    "message": "User-friendly message (e.g. syntax error at line X, or UTF-8 encoding required)",
                    "details": "file_path; for syntax: line, column (1-based), parser_message; for encoding: error_type, reason",
                },
            },
            "best_practices": [
                "Run file_structure before split_class or extract_superclass to see sizes",
                "Use line_count to identify large methods or classes for refactoring",
                "Use include_functions=false when only class layout is needed",
                "Combine with list_cst_blocks for stable block IDs when editing",
                "Use returned structure to build config for split_file_to_package",
            ],
        }
