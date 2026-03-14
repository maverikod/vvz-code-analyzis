"""
MCP command: list_class_methods.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .search import SearchCommand

logger = logging.getLogger(__name__)


class ListClassMethodsMCPCommand(BaseMCPCommand):
    """List all methods of a class."""

    name = "list_class_methods"
    version = "1.0.0"
    descr = "List all methods of a class"
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
                "class_name": {
                    "type": "string",
                    "description": "Name of the class",
                },
            },
            "required": ["project_id", "class_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        class_name: str,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute class methods listing."""
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                search_cmd = SearchCommand(database, project_id)
                methods = search_cmd.search_methods(class_name=class_name)

                return SuccessResult(
                    data={
                        "class_name": class_name,
                        "methods": methods,
                        "count": len(methods),
                    }
                )
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "list_class_methods")

    @classmethod
    def metadata(cls: type["ListClassMethodsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The list_class_methods command lists all methods of a specific class. "
                "It searches the database for all methods belonging to the specified class "
                "and returns their metadata including name, signature, file path, and line numbers.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Searches for class with given name\n"
                "5. Retrieves all methods belonging to that class\n"
                "6. Returns list of methods with metadata\n\n"
                "Method Information:\n"
                "- Method name\n"
                "- Method signature (parameters, return type)\n"
                "- File path where method is defined\n"
                "- Line numbers (start, end)\n"
                "- Class name\n"
                "- Docstring (if available)\n\n"
                "Use cases:\n"
                "- Explore class API\n"
                "- List all methods of a class\n"
                "- Find method locations\n"
                "- Understand class structure\n\n"
                "Important notes:\n"
                "- Requires built database (run update_indexes first)\n"
                "- Class name must match exactly (case-sensitive)\n"
                "- Returns all methods including inherited ones (if tracked)\n"
                "- Methods are returned in order of appearance in file"
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
                "class_name": {
                    "description": (
                        "Name of the class. Must match exactly (case-sensitive). "
                        "Returns all methods belonging to this class."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["MyClass", "DatabaseManager", "FileWatcher"],
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
                    "description": "List all methods of a class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "class_name": "MyClass",
                    },
                    "explanation": (
                        "Returns all methods of MyClass with their signatures, file paths, and line numbers."
                    ),
                },
                {
                    "description": "List methods with explicit project_id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "class_name": "DatabaseManager",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                    "explanation": (
                        "Lists methods of DatabaseManager class for the specified project."
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
                    "example": "Database error, class not found, or query error",
                    "solution": (
                        "Check database integrity, verify class name is correct, "
                        "ensure database was built with update_indexes."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "class_name": "Name of the class",
                        "methods": (
                            "List of methods. Each contains:\n"
                            "- name: Method name\n"
                            "- signature: Method signature (parameters, return type)\n"
                            "- file_path: Path to file containing the method\n"
                            "- line_start: Starting line number\n"
                            "- line_end: Ending line number\n"
                            "- docstring: Method docstring (if available)\n"
                            "- class_name: Name of the class"
                        ),
                        "count": "Number of methods found",
                    },
                    "example": {
                        "class_name": "MyClass",
                        "methods": [
                            {
                                "name": "process_data",
                                "signature": "def process_data(self, data: dict) -> bool",
                                "file_path": "src/my_class.py",
                                "line_start": 42,
                                "line_end": 55,
                                "docstring": "Process data and return result.",
                                "class_name": "MyClass",
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
                "Class name must match exactly (case-sensitive)",
                "Use find_classes first to discover available classes",
                "Empty result means class has no methods or class not found",
            ],
        }
