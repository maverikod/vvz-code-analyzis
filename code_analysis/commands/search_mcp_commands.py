"""
MCP command wrappers for search operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .search import SearchCommand

logger = logging.getLogger(__name__)


class FulltextSearchMCPCommand(BaseMCPCommand):
    """Perform full-text search in code content and docstrings."""

    name = "fulltext_search"
    version = "1.0.0"
    descr = "Perform full-text search in code content and docstrings"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Notes:
            This schema is used by MCP Proxy for request validation and tool routing.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Perform full-text search over indexed code content (FTS5) for a project. "
                "Requires a built database (run update_indexes/restore_database first)."
            ),
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                    "examples": ["/abs/path/to/project"],
                },
                "query": {
                    "type": "string",
                    "description": "Search query text",
                    "examples": ["structure analysis", "def solve", "MyClass"],
                },
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type (class, method, function)",
                    "examples": ["class"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 20,
                    "examples": [5, 20, 100],
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "query"],
            "additionalProperties": False,
            "examples": [
                {
                    "root_dir": "/abs/path/to/project",
                    "query": "structure analysis",
                    "limit": 5,
                },
                {
                    "root_dir": "/abs/path/to/project",
                    "query": "MyClass",
                    "entity_type": "class",
                    "limit": 20,
                },
            ],
        }

    async def execute(
        self,
        root_dir: str,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute full-text search.

        Args:
            root_dir: Root directory of the project
            query: Search query text
            entity_type: Optional filter by entity type
            limit: Maximum number of results
            project_id: Optional project UUID

        Returns:
            SuccessResult with search results or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not actual_project_id:
                    return ErrorResult(
                        message=(
                            f"Project not found: {project_id}"
                            if project_id
                            else "Failed to get or create project"
                        ),
                        code="PROJECT_NOT_FOUND",
                    )

                search_cmd = SearchCommand(database, actual_project_id)
                results = search_cmd.full_text_search(
                    query, entity_type=entity_type, limit=limit
                )

                return SuccessResult(
                    data={
                        "query": query,
                        "results": results,
                        "count": len(results),
                    }
                )
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "fulltext_search")


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
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "class_name": {
                    "type": "string",
                    "description": "Name of the class",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "class_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        class_name: str,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute class methods listing.

        Args:
            root_dir: Root directory of the project
            class_name: Name of the class
            project_id: Optional project UUID

        Returns:
            SuccessResult with methods list or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not actual_project_id:
                    return ErrorResult(
                        message=(
                            f"Project not found: {project_id}"
                            if project_id
                            else "Failed to get or create project"
                        ),
                        code="PROJECT_NOT_FOUND",
                    )

                search_cmd = SearchCommand(database, actual_project_id)
                # Pass class_name directly to search_methods
                methods = search_cmd.search_methods(class_name=class_name)

                return SuccessResult(
                    data={
                        "class_name": class_name,
                        "methods": methods,
                        "count": len(methods),
                    }
                )
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "list_class_methods")


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
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Name pattern to search (optional, if not provided returns all classes)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        pattern: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute class search.

        Args:
            root_dir: Root directory of the project
            pattern: Optional name pattern to search
            project_id: Optional project UUID

        Returns:
            SuccessResult with classes list or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not actual_project_id:
                    return ErrorResult(
                        message=(
                            f"Project not found: {project_id}"
                            if project_id
                            else "Failed to get or create project"
                        ),
                        code="PROJECT_NOT_FOUND",
                    )

                search_cmd = SearchCommand(database, actual_project_id)
                classes = search_cmd.search_classes(pattern)

                return SuccessResult(
                    data={
                        "pattern": pattern,
                        "classes": classes,
                        "count": len(classes),
                    }
                )
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "find_classes")
