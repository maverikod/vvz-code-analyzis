"""
MCP command wrappers for search operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..core import CodeDatabase
from .search import SearchCommand

logger = logging.getLogger(__name__)


def _open_database(root_dir: str) -> CodeDatabase:
    """Open database for project."""
    root_path = Path(root_dir).resolve()
    data_dir = root_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "code_analysis.db"
    return CodeDatabase(db_path)


def _get_project_id(
    db: CodeDatabase, root_path: Path, project_id: Optional[str]
) -> Optional[str]:
    """Get or create project ID."""
    if project_id:
        project = db.get_project(project_id)
        if not project:
            return None
        return project_id
    return db.get_or_create_project(str(root_path), name=root_path.name)


class FulltextSearchMCPCommand(Command):
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
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type (class, method, function)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 20,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "query"],
            "additionalProperties": False,
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
            root_path = Path(root_dir).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return ErrorResult(
                    message=f"Root directory does not exist or is not a directory: {root_dir}",
                    code="INVALID_PATH",
                )

            database = _open_database(root_dir)
            try:
                actual_project_id = _get_project_id(database, root_path, project_id)
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
            logger.exception(f"Error during full-text search: {e}")
            return ErrorResult(
                message=f"Full-text search failed: {str(e)}",
                code="SEARCH_ERROR",
                details={"error": str(e)},
            )


class ListClassMethodsMCPCommand(Command):
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
            root_path = Path(root_dir).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return ErrorResult(
                    message=f"Root directory does not exist or is not a directory: {root_dir}",
                    code="INVALID_PATH",
                )

            database = _open_database(root_dir)
            try:
                actual_project_id = _get_project_id(database, root_path, project_id)
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
                all_methods = search_cmd.search_methods(None)
                methods = [m for m in all_methods if m.get("class_name") == class_name]

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
            logger.exception(f"Error listing class methods: {e}")
            return ErrorResult(
                message=f"Failed to list class methods: {str(e)}",
                code="SEARCH_ERROR",
                details={"error": str(e)},
            )


class FindClassesMCPCommand(Command):
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
            root_path = Path(root_dir).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return ErrorResult(
                    message=f"Root directory does not exist or is not a directory: {root_dir}",
                    code="INVALID_PATH",
                )

            database = _open_database(root_dir)
            try:
                actual_project_id = _get_project_id(database, root_path, project_id)
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
            logger.exception(f"Error finding classes: {e}")
            return ErrorResult(
                message=f"Failed to find classes: {str(e)}",
                code="SEARCH_ERROR",
                details={"error": str(e)},
            )
