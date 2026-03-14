"""
MCP command: find_classes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .search import SearchCommand

logger = logging.getLogger(__name__)


class FindClassesMCPCommand(BaseMCPCommand):
    """Find classes by name pattern."""

    name = "find_classes"
    version = "1.0.0"
    descr = "Find classes by name pattern"
    category = "search"
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
                "pattern": {
                    "type": "string",
                    "description": "Name pattern to search (optional, if not provided returns all classes)",
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        pattern: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute class search."""
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                search_cmd = SearchCommand(database, project_id)
                classes = search_cmd.search_classes(pattern)

                return SuccessResult(
                    data={
                        "pattern": pattern,
                        "classes": classes,
                        "count": len(classes),
                    }
                )
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "find_classes")

    @classmethod
    def metadata(cls: type["FindClassesMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "parameters_summary": (
                "Required: project_id. Optional: pattern (SQL LIKE name pattern; "
                "e.g. '%Manager'. No 'limit' parameter.)"
            ),
            "detailed_description": (
                "The find_classes command searches for classes by name pattern. "
                "It can search for classes matching a specific pattern or return all classes "
                "if no pattern is provided.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Searches for classes matching the pattern (if provided)\n"
                "5. If no pattern provided, returns all classes\n"
                "6. Returns list of classes with metadata\n\n"
                "Pattern Matching:\n"
                "- Supports SQL LIKE pattern matching\n"
                "- Use '%' for wildcard (e.g., '%Manager' matches 'DatabaseManager')\n"
                "- Use '_' for single character wildcard\n"
                "- Case-sensitive matching\n"
                "- If pattern is None, returns all classes\n\n"
                "Class Information:\n"
                "- Class name\n"
                "- File path where class is defined\n"
                "- Line numbers (start, end)\n"
                "- Docstring (if available)\n"
                "- Base classes (if available)\n\n"
                "Use cases:\n"
                "- Find classes by name pattern\n"
                "- Discover all classes in project\n"
                "- Search for classes with specific naming convention\n"
                "- Explore project structure\n\n"
                "Important notes:\n"
                "- Requires built database (run update_indexes first)\n"
                "- Pattern uses SQL LIKE syntax\n"
                "- If pattern is None, returns all classes (may be large result set)\n"
                "- Results are sorted by class name"
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
                "pattern": {
                    "description": (
                        "Optional name pattern to search. Uses SQL LIKE syntax. "
                        "Use '%' for wildcard (e.g., '%Manager' matches 'DatabaseManager'). "
                        "If not provided, returns all classes."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "Manager",
                        "%Manager",
                        "Base%",
                        "%Handler%",
                    ],
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Find all classes",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns all classes in the project. May return large result set."
                    ),
                },
                {
                    "description": "Find classes by pattern",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "pattern": "%Manager",
                    },
                    "explanation": (
                        "Returns all classes ending with 'Manager' (e.g., 'DatabaseManager', 'FileManager')."
                    ),
                },
                {
                    "description": "Find classes starting with pattern",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "pattern": "Base%",
                    },
                    "explanation": (
                        "Returns all classes starting with 'Base' (e.g., 'BaseClass', 'BaseHandler')."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "SEARCH_ERROR": {
                    "description": "General error during search",
                    "example": "Database error, pattern syntax error, or query error",
                    "solution": (
                        "Check database integrity, verify pattern syntax (SQL LIKE), "
                        "ensure database was built with update_indexes."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "pattern": "Pattern that was used (or None)",
                        "classes": (
                            "List of classes. Each contains:\n"
                            "- name: Class name\n"
                            "- file_path: Path to file containing the class\n"
                            "- line_start: Starting line number\n"
                            "- line_end: Ending line number\n"
                            "- docstring: Class docstring (if available)\n"
                            "- base_classes: List of base classes (if available)"
                        ),
                        "count": "Number of classes found",
                    },
                    "example": {
                        "pattern": "%Manager",
                        "classes": [
                            {
                                "name": "DatabaseManager",
                                "file_path": "src/db.py",
                                "line_start": 10,
                                "line_end": 50,
                                "docstring": "Manages database connections.",
                                "base_classes": ["BaseManager"],
                            },
                        ],
                        "count": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, SEARCH_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run update_indexes first to build the database",
                "Use pattern to narrow down results (avoid returning all classes)",
                "Pattern uses SQL LIKE syntax with '%' and '_' wildcards",
                "Use list_class_methods after finding a class to explore its methods",
                "Empty result means no classes match the pattern",
            ],
        }
