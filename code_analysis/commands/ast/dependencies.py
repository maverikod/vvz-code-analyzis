"""
MCP command wrapper: find_dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class FindDependenciesMCPCommand(BaseMCPCommand):
    """Find dependencies - where classes, functions, or modules are used."""

    name = "find_dependencies"
    version = "1.0.0"
    descr = "Find where a class, function, method, or module is used in the project"
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "entity_name": {
                    "type": "string",
                    "description": "Name of entity to find dependencies for",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', 'method', 'module', or null for all",
                    "enum": ["class", "function", "method", "module"],
                },
                "target_class": {
                    "type": "string",
                    "description": "Optional class name for methods",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of results",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "entity_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_name: str,
        entity_type: Optional[str] = None,
        target_class: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Find dependencies from database
            # Uses multiple sources for comprehensive results:
            # - usages table: actual function calls, method calls, class instantiations
            # - imports table: module/class/function imports
            # - classes table: inheritance relationships (bases)
            results = []
            import json

            # Search in imports table for class/function/module dependencies
            if entity_type in ("class", "function", "module", None):
                import_query = """
                    SELECT i.*, f.path as file_path
                    FROM imports i
                    JOIN files f ON i.file_id = f.id
                    WHERE f.project_id = ? AND (i.name = ? OR i.module LIKE ?)
                """
                import_params = [proj_id, entity_name, f"%{entity_name}%"]

                import_query += " ORDER BY f.path, i.line"
                if limit:
                    import_query += f" LIMIT {limit}"
                if offset:
                    import_query += f" OFFSET {offset}"

                result = db.execute(import_query, tuple(import_params))
                import_rows = result.get("data", [])
                for row in import_rows:
                    results.append(
                        {
                            "type": "import",
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "module": row.get("module"),
                            "name": row["name"],
                            "import_type": row["import_type"],
                        }
                    )

            # For classes: also search for inheritance (classes that inherit from this class)
            if entity_type in ("class", None):
                inheritance_query = """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ? AND c.bases LIKE ?
                """
                inheritance_params = [proj_id, f"%{entity_name}%"]

                inheritance_query += " ORDER BY f.path, c.line"
                if limit:
                    # Apply limit to total results, not just this query
                    inheritance_query += (
                        f" LIMIT {limit * 2}"  # Get more to account for imports
                    )
                if offset:
                    inheritance_query += f" OFFSET {offset}"

                result = db.execute(inheritance_query, tuple(inheritance_params))
                inheritance_rows = result.get("data", [])
                for row in inheritance_rows:
                    # Parse bases JSON to check if entity_name is in bases
                    bases = []
                    if row.get("bases"):
                        try:
                            bases = json.loads(row["bases"])
                        except (json.JSONDecodeError, TypeError):
                            bases = []

                    if entity_name in bases:
                        results.append(
                            {
                                "type": "inheritance",
                                "file_path": row["file_path"],
                                "line": row["line"],
                                "class_name": row["name"],
                                "bases": bases,
                            }
                        )

            # Also try usages table (may be empty, but check anyway)
            if entity_type in ("class", "function", "method", None):
                usage_query = """
                    SELECT u.*, f.path as file_path
                    FROM usages u
                    JOIN files f ON u.file_id = f.id
                    WHERE f.project_id = ? AND u.target_name = ?
                """
                usage_params = [proj_id, entity_name]

                if entity_type:
                    usage_query += " AND u.target_type = ?"
                    usage_params.append(entity_type)

                if target_class:
                    usage_query += " AND u.target_class = ?"
                    usage_params.append(target_class)

                usage_query += " ORDER BY f.path, u.line"
                if limit:
                    usage_query += f" LIMIT {limit}"
                if offset:
                    usage_query += f" OFFSET {offset}"

                result = db.execute(usage_query, tuple(usage_params))
                usage_rows = result.get("data", [])
                for row in usage_rows:
                    results.append(
                        {
                            "type": "usage",
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "target_name": row["target_name"],
                            "target_type": row["target_type"],
                            "target_class": row.get("target_class"),
                        }
                    )

            # Apply limit and offset to final results
            if limit:
                results = results[offset : offset + limit]
            elif offset:
                results = results[offset:]

            db.disconnect()

            return SuccessResult(
                data={
                    "success": True,
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "dependencies": results,
                    "count": len(results),
                }
            )
        except Exception as e:
            return self._handle_error(e, "FIND_DEPENDENCIES_ERROR", "find_dependencies")

    @classmethod
    def metadata(cls: type["FindDependenciesMCPCommand"]) -> Dict[str, Any]:
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
                "The find_dependencies command finds where a class, function, method, or module "
                "is used (depended upon) in the project. It searches through usages and imports "
                "tables to find all locations where the entity is referenced.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Searches usages table for entity usages (if entity_type is class/function/method/null)\n"
                "5. Searches imports table for module dependencies (if entity_type is module/null)\n"
                "6. Applies filters: entity_name, entity_type, target_class\n"
                "7. Applies pagination: limit and offset\n"
                "8. Returns list of dependency locations with file paths and line numbers\n\n"
                "Search Behavior:\n"
                "- For classes/functions/methods: Searches in usages table where target_name matches\n"
                "- For modules: Searches in imports table where module or name matches\n"
                "- If entity_type is null, searches both usages and imports\n"
                "- Results include file path, line number, and entity details\n\n"
                "Use cases:\n"
                "- Find all places where a class is instantiated or used\n"
                "- Find all places where a function is called\n"
                "- Find all places where a method is called\n"
                "- Find all files that import a specific module\n"
                "- Impact analysis before refactoring\n"
                "- Dependency tracking and code navigation\n\n"
                "Important notes:\n"
                "- Results are ordered by file path and line number\n"
                "- Supports pagination with limit and offset\n"
                "- For methods, use target_class parameter to disambiguate\n"
                "- Module search uses LIKE pattern matching for partial matches"
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
                "entity_name": {
                    "description": (
                        "Name of entity to find dependencies for. Required. "
                        "Can be class name, function name, method name, or module name."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["MyClass", "process_data", "calculate", "os"],
                },
                "entity_type": {
                    "description": (
                        "Type of entity to search for. Optional. If null, searches all types. "
                        "Options: 'class', 'function', 'method', 'module'. "
                        "Helps narrow search and improve performance."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["class", "function", "method", "module"],
                },
                "target_class": {
                    "description": (
                        "Optional class name for methods. Use when searching for methods "
                        "to disambiguate methods with same name in different classes."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["MyClass", "BaseHandler"],
                },
                "limit": {
                    "description": (
                        "Optional limit on number of results. Use for pagination or "
                        "to limit large result sets."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "offset": {
                    "description": (
                        "Offset for pagination. Default is 0. Use with limit for paginated results."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 0,
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
                    "description": "Find all usages of a class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_name": "DataProcessor",
                        "entity_type": "class",
                    },
                    "explanation": (
                        "Finds all places where DataProcessor class is used, instantiated, "
                        "or referenced in the project."
                    ),
                },
                {
                    "description": "Find all calls to a function",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_name": "process_data",
                        "entity_type": "function",
                    },
                    "explanation": (
                        "Finds all function calls to process_data across the project."
                    ),
                },
                {
                    "description": "Find method usages with class context",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_name": "execute",
                        "entity_type": "method",
                        "target_class": "TaskHandler",
                    },
                    "explanation": (
                        "Finds all calls to execute method specifically in TaskHandler class, "
                        "excluding execute methods in other classes."
                    ),
                },
                {
                    "description": "Find module imports with pagination",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_name": "os",
                        "entity_type": "module",
                        "limit": 50,
                        "offset": 0,
                    },
                    "explanation": (
                        "Finds first 50 files that import 'os' module. Use offset for next page."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "FIND_DEPENDENCIES_ERROR": {
                    "description": "General error during dependency search",
                    "example": "Database error, invalid parameters, or corrupted data",
                    "solution": (
                        "Check database integrity, verify entity_name and entity_type parameters, "
                        "ensure project has been analyzed."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "entity_name": "Entity name that was searched",
                        "entity_type": "Entity type that was searched (or null)",
                        "dependencies": (
                            "List of dependency dictionaries. Each contains:\n"
                            "- type: 'usage' or 'import'\n"
                            "- file_path: File where dependency occurs\n"
                            "- line: Line number where dependency occurs\n"
                            "- For usages: target_name, target_type, target_class\n"
                            "- For imports: module, name, import_type"
                        ),
                        "count": "Number of dependencies found",
                    },
                    "example": {
                        "success": True,
                        "entity_name": "DataProcessor",
                        "entity_type": "class",
                        "dependencies": [
                            {
                                "type": "usage",
                                "file_path": "src/main.py",
                                "line": 42,
                                "target_name": "DataProcessor",
                                "target_type": "class",
                                "target_class": None,
                            },
                            {
                                "type": "usage",
                                "file_path": "src/utils.py",
                                "line": 15,
                                "target_name": "DataProcessor",
                                "target_type": "class",
                                "target_class": None,
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FIND_DEPENDENCIES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Specify entity_type to narrow search and improve performance",
                "Use target_class parameter when searching for methods to avoid false matches",
                "Use limit and offset for pagination when dealing with many results",
                "Use this command for impact analysis before refactoring",
                "Combine with find_usages for comprehensive dependency tracking",
            ],
        }
