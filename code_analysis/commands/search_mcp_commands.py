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

    @classmethod
    def metadata(cls: type["FulltextSearchMCPCommand"]) -> Dict[str, Any]:
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
                "The fulltext_search command performs full-text search over indexed code content "
                "using SQLite FTS5 (Full-Text Search 5). It searches through code content, docstrings, "
                "and entity names to find matches for the query text.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Performs FTS5 search in code_chunks_fts table\n"
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

    @classmethod
    def metadata(cls: type["ListClassMethodsMCPCommand"]) -> Dict[str, Any]:
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

    @classmethod
    def metadata(cls: type["FindClassesMCPCommand"]) -> Dict[str, Any]:
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
