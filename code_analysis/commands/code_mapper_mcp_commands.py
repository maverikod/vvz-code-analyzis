"""
MCP commands for code_mapper functionality (long files, errors by category).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..core.constants import DEFAULT_MAX_FILE_LINES
from .base_mcp_command import BaseMCPCommand
from .code_mapper_commands import ListLongFilesCommand, ListErrorsByCategoryCommand
from .file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)

logger = logging.getLogger(__name__)


class ListLongFilesMCPCommand(BaseMCPCommand):
    """
    MCP command to list files exceeding line limit.

    Equivalent to old code_mapper functionality for finding oversized files.
    """

    name = "list_long_files"
    version = "1.0.0"
    descr = (
        "List files exceeding a line threshold; optional ``file_pattern`` / ``glob`` on "
        "project-relative paths (fnmatch / prefix, same as list_project_files)"
    )
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": (
                "List indexed project files whose ``lines`` exceed ``max_lines``. "
                "Optional ``file_pattern`` / ``glob`` filter on paths normalized relative to "
                "project root. **No** ``limit``/``offset`` — the full filtered list is returned."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines threshold (default: 400)",
                    "default": 400,
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional fnmatch on each row's ``path`` from the database after "
                        "normalizing to a project-relative POSIX string (``*`` crosses ``/``). "
                        "``glob`` is an alias."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Alias of ``file_pattern``; non-empty ``file_pattern`` wins when both set."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        max_lines: int = DEFAULT_MAX_FILE_LINES,
        file_pattern: Optional[str] = None,
        glob: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list long files command.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            max_lines: Maximum lines threshold

        Returns:
            SuccessResult with long files list or ErrorResult on failure
        """
        try:
            root = self._resolve_project_root(project_id)
            db = self._open_database_from_config(auto_analyze=False)

            command = ListLongFilesCommand(db, project_id, max_lines)
            result = await command.execute()
            db.disconnect()

            eff = effective_listing_pattern(file_pattern, glob)
            if eff and isinstance(result, dict):
                files = result.get("files") or []
                out = []
                for f in files:
                    raw_path = f.get("path")
                    if not raw_path:
                        continue
                    rel = canonical_relative_path(root, Path(str(raw_path)))
                    if relative_path_matches_listing_pattern(rel, eff):
                        out.append(f)
                result = {**result, "files": out, "count": len(out)}

            return SuccessResult(data=result)

        except Exception as e:
            return self._handle_error(e, "LIST_LONG_FILES_ERROR", "list_long_files")

    @classmethod
    def metadata(cls: type["ListLongFilesMCPCommand"]) -> Dict[str, Any]:
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
                "The list_long_files command lists all files in a project that exceed the maximum "
                "line limit. This is equivalent to old code_mapper functionality for finding oversized files. "
                "Large files are harder to maintain and may need to be split into smaller modules.\n\n"
                "Operation flow:\n"
                "1. Resolves project root from ``project_id``\n"
                "2. Opens database connection\n"
                "3. Queries files table for project files with lines > ``max_lines``\n"
                "4. Optionally filters rows where the DB path matches ``file_pattern`` / ``glob`` "
                "(fnmatch on project-relative path; same rules as ``list_project_files``)\n"
                "5. Returns list of files exceeding the threshold\n\n"
                "Use cases:\n"
                "- Identify files that need to be split\n"
                "- Monitor file size compliance\n"
                "- Find oversized files before refactoring\n"
                "- Enforce file size limits\n\n"
                "Important notes:\n"
                "- Uses line count from database (updated during indexing)\n"
                "- Default threshold is 400 lines (project standard)\n"
                "- Files are sorted by line count (descending)\n"
                "- No pagination: all matching long files are returned in one response\n"
                "- Equivalent to code_mapper functionality"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID (from create_project or list_projects). Required."
                    ),
                    "type": "string",
                    "required": True,
                },
                "max_lines": {
                    "description": (
                        "Maximum lines threshold. Default is 400. Files exceeding this threshold "
                        "are reported as long files."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 400,
                },
                "file_pattern": {
                    "description": (
                        "Optional fnmatch on each file path resolved relative to project root. "
                        "``glob`` is an alias."
                    ),
                    "type": "string",
                    "required": False,
                },
                "glob": {
                    "description": "Alias of ``file_pattern``.",
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List files exceeding 400 lines (default)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": (
                        "Lists all files in project exceeding 400 lines (default threshold)."
                    ),
                },
                {
                    "description": "Long Python files under a subtree",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "max_lines": 300,
                        "file_pattern": "code_analysis/**/*.py",
                    },
                    "explanation": ("Combines line threshold with path glob."),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "Unknown project_id",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "LIST_LONG_FILES_ERROR": {
                    "description": "General error during file listing",
                    "example": "Database error or invalid parameters",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project has been indexed."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "files": (
                            "List of files exceeding max_lines. Each entry contains:\n"
                            "- path: File path\n"
                            "- lines: Number of lines in file\n"
                            "- Additional file metadata from database"
                        ),
                        "count": "Number of long files found",
                        "max_lines": "Maximum lines threshold used",
                    },
                    "example": {
                        "success": True,
                        "files": [
                            {"path": "src/main.py", "lines": 450},
                            {"path": "src/utils.py", "lines": 520},
                        ],
                        "count": 2,
                        "max_lines": 400,
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, LIST_LONG_FILES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                f"Use default max_lines={DEFAULT_MAX_FILE_LINES} to follow project standards",
                "Use file_pattern or glob to scope long files to a subtree (fnmatch on full path)",
                "Run this command regularly to monitor file sizes",
                "Use split_file_to_package to split large files",
                "Combine with comprehensive_analysis for complete code quality overview",
            ],
        }


class ListErrorsByCategoryMCPCommand(BaseMCPCommand):
    """
    MCP command to list errors grouped by category.

    Equivalent to old code_mapper functionality for listing code issues.
    """

    name = "list_errors_by_category"
    version = "1.0.0"
    descr = "List code errors grouped by category (code_mapper functionality)"
    category = "analysis"
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
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list errors by category command.

        Args:
            project_id: Optional project UUID (all projects if None).

        Returns:
            SuccessResult with errors grouped by category or ErrorResult on failure
        """
        try:
            if project_id:
                self._resolve_project_root(project_id)
            db = self._open_database_from_config(auto_analyze=False)

            command = ListErrorsByCategoryCommand(db, project_id)
            result = await command.execute()
            db.disconnect()

            return SuccessResult(data=result)

        except Exception as e:
            return self._handle_error(e, "LIST_ERRORS_ERROR", "list_errors_by_category")

    @classmethod
    def metadata(cls: type["ListErrorsByCategoryMCPCommand"]) -> Dict[str, Any]:
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
                "The list_errors_by_category command lists code errors grouped by category. "
                "This is equivalent to old code_mapper functionality for listing code issues. "
                "It provides a categorized view of all code quality issues in the project.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. If project_id is None, lists errors from all projects\n"
                "5. Queries issues table grouped by issue_type\n"
                "6. Aggregates issues by category\n"
                "7. Creates summary statistics\n"
                "8. Returns categorized errors with summary\n\n"
                "Use cases:\n"
                "- Get overview of code quality issues by category\n"
                "- Identify most common issue types\n"
                "- Track code quality metrics\n"
                "- Generate code quality reports\n\n"
                "Important notes:\n"
                "- If project_id is None, returns errors from all projects\n"
                "- Issues are grouped by issue_type (category)\n"
                "- Summary includes counts per category and total\n"
                "- Equivalent to code_mapper functionality"
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
                        "Optional project UUID. If omitted, inferred from root_dir. "
                        "If project not found, lists errors from all projects."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List errors for specific project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Lists all code errors grouped by category for the project."
                    ),
                },
                {
                    "description": "List errors from all projects",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": None,
                    },
                    "explanation": (
                        "Lists errors from all projects in the database (if project not found)."
                    ),
                },
            ],
            "error_cases": {
                "LIST_ERRORS_ERROR": {
                    "description": "General error during error listing",
                    "example": "Database error or invalid parameters",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project has been indexed."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "categories": (
                            "Dictionary mapping issue_type to list of issues. "
                            "Each issue contains file path, line number, and issue details."
                        ),
                        "summary": (
                            "Summary statistics dictionary with:\n"
                            "- Counts per category (issue_type)\n"
                            "- total: Total number of issues"
                        ),
                        "total": "Total number of issues found",
                    },
                    "example": {
                        "categories": {
                            "missing_docstring": [
                                {
                                    "file_path": "src/main.py",
                                    "line": 10,
                                    "type": "class",
                                },
                            ],
                            "long_file": [
                                {"file_path": "src/utils.py", "lines": 450},
                            ],
                        },
                        "summary": {
                            "missing_docstring": 1,
                            "long_file": 1,
                            "total": 2,
                        },
                        "total": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., LIST_ERRORS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use this command to get overview of code quality issues",
                "Review summary statistics first, then drill down into specific categories",
                "Combine with comprehensive_analysis for detailed issue analysis",
                "Use for tracking code quality trends over time",
            ],
        }
