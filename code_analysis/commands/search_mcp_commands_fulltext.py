"""
MCP command: fulltext_search.

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
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": (
                "Perform full-text search over indexed code content (FTS5) for a project. "
                "Requires a built database (run update_indexes/restore_database first)."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
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
            },
            "required": ["project_id", "query"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "query": "structure analysis",
                    "limit": 5,
                },
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "query": "MyClass",
                    "entity_type": "class",
                    "limit": 20,
                },
            ],
        }

    async def execute(
        self,
        project_id: str,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute full-text search."""
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                search_cmd = SearchCommand(database, project_id)
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
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "fulltext_search")

    @classmethod
    def metadata(cls: type["FulltextSearchMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The fulltext_search command performs full-text search over indexed code content "
                "using SQLite FTS5 (Full-Text Search 5). It searches through code content, docstrings, "
                "and entity names to find matches for the query text.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Performs FTS5 search in code_content_fts table (BM25 ranking)\n"
                "5. Filters by entity_type if provided (class, method, function)\n"
                "6. Limits results to specified limit\n"
                "7. Returns matching chunks with file paths and metadata\n\n"
                "Search Capabilities:\n"
                "- Searches in code content (chunk_text)\n"
                "- Searches in docstrings\n"
                "- Searches in entity names\n"
                "- Supports partial word matching\n"
                "- Case-insensitive search\n"
                "- Can filter by entity type\n\n"
                "Use cases:\n"
                "- Find code containing specific text\n"
                "- Search for function/class names\n"
                "- Find code with specific patterns\n"
                "- Search in docstrings\n\n"
                "Important notes:\n"
                "- Requires built database (run update_indexes first)\n"
                "- Uses SQLite FTS5 for fast text search\n"
                "- Results are ranked by relevance\n"
                "- Default limit is 20 results\n"
                "- Entity type filter: 'class', 'method', or 'function'"
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
                "query": {
                    "description": (
                        "Search query text. Searches in code content, docstrings, and entity names. "
                        "Supports partial word matching and is case-insensitive."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "structure analysis",
                        "def solve",
                        "MyClass",
                        "database connection",
                    ],
                },
                "entity_type": {
                    "description": (
                        "Optional filter by entity type. Options: 'class', 'method', 'function'. "
                        "If not provided, searches all entity types."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["class", "method", "function"],
                    "examples": ["class", "method"],
                },
                "limit": {
                    "description": (
                        "Maximum number of results to return. Default is 20. "
                        "Results are ranked by relevance."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 20,
                    "examples": [5, 20, 100],
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
                    "description": "Search for text in code",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "query": "structure analysis",
                        "limit": 10,
                    },
                    "explanation": (
                        "Searches for 'structure analysis' in all code content and docstrings, "
                        "returning up to 10 results."
                    ),
                },
                {
                    "description": "Search for classes",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "query": "MyClass",
                        "entity_type": "class",
                    },
                    "explanation": (
                        "Searches for classes containing 'MyClass' in their name or content."
                    ),
                },
                {
                    "description": "Search for function definitions",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "query": "def solve",
                        "entity_type": "function",
                    },
                    "explanation": (
                        "Searches for functions containing 'solve' in their name or content."
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
                    "example": "Database error, FTS5 not available, or query parsing error",
                    "solution": (
                        "Check database integrity, ensure FTS5 is enabled, "
                        "verify database was built with update_indexes."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "query": "Search query that was used",
                        "results": (
                            "List of matching chunks. Each contains:\n"
                            "- chunk_uuid: Chunk UUID\n"
                            "- chunk_type: Type of chunk (class, method, function, etc.)\n"
                            "- chunk_text: Text content of chunk\n"
                            "- file_path: Path to file containing the chunk\n"
                            "- line: Line number in file\n"
                            "- rank: Relevance rank (lower is better)"
                        ),
                        "count": "Number of results found",
                    },
                    "example": {
                        "query": "structure analysis",
                        "results": [
                            {
                                "chunk_uuid": "abc123...",
                                "chunk_type": "function",
                                "chunk_text": "def analyze_structure(...)",
                                "file_path": "src/analyzer.py",
                                "line": 42,
                                "rank": 1,
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
                "Run update_indexes first to build the search index",
                "Use entity_type filter to narrow down results",
                "Adjust limit based on expected result count",
                "Query text supports partial word matching",
                "Results are ranked by relevance",
            ],
        }
