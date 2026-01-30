"""
MCP command wrapper: find_usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class FindUsagesMCPCommand(BaseMCPCommand):
    """Find usages of methods, properties, classes, or functions."""

    name = "find_usages"
    version = "1.0.0"
    descr = "Find where a method, property, class, or function is used in the project"
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
                "target_name": {
                    "type": "string",
                    "description": "Name of target to find usages for",
                },
                "target_type": {
                    "type": "string",
                    "description": "Type of target: 'method', 'property', 'class', 'function', or null for all",
                    "enum": ["method", "property", "class", "function"],
                },
                "target_class": {
                    "type": "string",
                    "description": "Optional class name for methods/properties",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (where usage occurs)",
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
            "required": ["root_dir", "target_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        target_name: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
        file_path: Optional[str] = None,
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

            # Find usages from database
            # Uses multiple sources for comprehensive results:
            # - usages table: actual function calls, method calls, class instantiations
            # - imports table: module/class/function imports
            # - classes table: inheritance relationships (bases)
            usages = []
            import json

            # Search in imports table for class/function usages
            if target_type in ("class", "function", None):
                import_query = """
                    SELECT i.*, f.path as file_path, f.id as file_id
                    FROM imports i
                    JOIN files f ON i.file_id = f.id
                    WHERE f.project_id = ? AND i.name = ?
                """
                import_params = [proj_id, target_name]

                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        import_query += " AND i.file_id = ?"
                        import_params.append(file_record["id"])

                import_query += " ORDER BY f.path, i.line"
                if limit:
                    import_query += f" LIMIT {limit}"
                if offset:
                    import_query += f" OFFSET {offset}"

                result = db.execute(import_query, tuple(import_params))
                import_rows = result.get("data", [])
                for row in import_rows:
                    usages.append(
                        {
                            "file_id": row["file_id"],
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "target_name": row["name"],
                            "target_type": target_type or "import",
                            "target_class": None,
                            "usage_type": "import",
                            "module": row.get("module"),
                            "import_type": row["import_type"],
                        }
                    )

            # For classes: search for inheritance (classes that inherit from target)
            if target_type in ("class", None):
                inheritance_query = """
                    SELECT c.*, f.path as file_path, f.id as file_id
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ? AND c.bases LIKE ?
                """
                inheritance_params = [proj_id, f"%{target_name}%"]

                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        inheritance_query += " AND c.file_id = ?"
                        inheritance_params.append(file_record["id"])

                inheritance_query += " ORDER BY f.path, c.line"
                if limit:
                    inheritance_query += (
                        f" LIMIT {limit * 2}"  # Get more to account for imports
                    )
                if offset:
                    inheritance_query += f" OFFSET {offset}"

                result = db.execute(inheritance_query, tuple(inheritance_params))
                inheritance_rows = result.get("data", [])
                for row in inheritance_rows:
                    # Parse bases JSON to check if target_name is in bases
                    bases = []
                    if row.get("bases"):
                        try:
                            bases = json.loads(row["bases"])
                        except (json.JSONDecodeError, TypeError):
                            bases = []

                    if target_name in bases:
                        usages.append(
                            {
                                "file_id": row["file_id"],
                                "file_path": row["file_path"],
                                "line": row["line"],
                                "target_name": target_name,
                                "target_type": "class",
                                "target_class": None,
                                "usage_type": "inheritance",
                                "class_name": row["name"],
                                "bases": bases,
                            }
                        )

            # Also try usages table (may be empty, but check anyway)
            query = """
                SELECT u.*, f.path as file_path, f.id as file_id
                FROM usages u
                JOIN files f ON u.file_id = f.id
                WHERE f.project_id = ?
            """
            params = [proj_id]

            if target_name:
                query += " AND u.target_name = ?"
                params.append(target_name)

            if target_type:
                query += " AND u.target_type = ?"
                params.append(target_type)

            if target_class:
                query += " AND u.target_class = ?"
                params.append(target_class)

            if file_path:
                file_record = db.get_file_by_path(file_path, proj_id)
                if file_record:
                    query += " AND u.file_id = ?"
                    params.append(file_record["id"])

            query += " ORDER BY f.path, u.line"

            if limit:
                query += f" LIMIT {limit}"
            if offset:
                query += f" OFFSET {offset}"

            result = db.execute(query, tuple(params))
            usage_rows = result.get("data", [])
            for row in usage_rows:
                usages.append(
                    {
                        "file_id": row["file_id"],
                        "file_path": row["file_path"],
                        "line": row["line"],
                        "target_name": row["target_name"],
                        "target_type": row["target_type"],
                        "target_class": row.get("target_class"),
                        "usage_type": row.get("usage_type", "usage"),
                        "context": row.get("context"),
                    }
                )

            # Apply limit and offset to final results
            if limit:
                usages = usages[offset : offset + limit]
            elif offset:
                usages = usages[offset:]

            db.disconnect()

            return SuccessResult(
                data={
                    "success": True,
                    "target_name": target_name,
                    "usages": usages,
                    "count": len(usages),
                }
            )
        except Exception as e:
            return self._handle_error(e, "FIND_USAGES_ERROR", "find_usages")

    @classmethod
    def metadata(cls: type["FindUsagesMCPCommand"]) -> Dict[str, Any]:
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
                "The find_usages command finds all places where a method, property, class, or function "
                "is used in the project. It searches the usages table in the analysis database to "
                "locate all references to the target entity.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Builds query filtering by target_name, target_type, target_class, file_path\n"
                "5. If file_path provided, limits search to that specific file\n"
                "6. Applies pagination: limit and offset\n"
                "7. Returns list of usages with file paths and line numbers\n\n"
                "Search Behavior:\n"
                "- Searches usages table for exact matches on target_name\n"
                "- Can filter by target_type (method/property/class/function)\n"
                "- Can filter by target_class for methods/properties\n"
                "- Can filter by file_path to limit scope\n"
                "- Results ordered by file_id and line number\n\n"
                "Use cases:\n"
                "- Find all places where a function is called\n"
                "- Find all places where a class is used\n"
                "- Find all places where a method is called\n"
                "- Find all places where a property is accessed\n"
                "- Code navigation and refactoring support\n"
                "- Impact analysis before changes\n\n"
                "Important notes:\n"
                "- Results include file_id, not just file_path (use get_file_by_path to resolve)\n"
                "- Supports pagination with limit and offset\n"
                "- For methods, use target_class to disambiguate\n"
                "- If file_path provided, searches only in that file"
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
                "target_name": {
                    "description": (
                        "Name of target to find usages for. Required. "
                        "Can be method name, property name, class name, or function name."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["process", "execute", "MyClass", "calculate"],
                },
                "target_type": {
                    "description": (
                        "Type of target to search for. Optional. If null, searches all types. "
                        "Options: 'method', 'property', 'class', 'function'. "
                        "Helps narrow search and improve performance."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["method", "property", "class", "function"],
                },
                "target_class": {
                    "description": (
                        "Optional class name for methods/properties. Use when searching for methods "
                        "or properties to disambiguate entities with same name in different classes."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["TaskHandler", "DataProcessor"],
                },
                "file_path": {
                    "description": (
                        "Optional file path to filter by. If provided, only searches for usages "
                        "within this specific file. Can be absolute or relative to root_dir."
                    ),
                    "type": "string",
                    "required": False,
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
                    "description": "Find all usages of a function",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "target_name": "process_data",
                        "target_type": "function",
                    },
                    "explanation": (
                        "Finds all places where process_data function is called across the project."
                    ),
                },
                {
                    "description": "Find method usages with class context",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "target_name": "execute",
                        "target_type": "method",
                        "target_class": "TaskHandler",
                    },
                    "explanation": (
                        "Finds all calls to execute method specifically in TaskHandler class."
                    ),
                },
                {
                    "description": "Find usages in specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "target_name": "MyClass",
                        "target_type": "class",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Finds all usages of MyClass only within src/main.py file."
                    ),
                },
                {
                    "description": "Find usages with pagination",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "target_name": "calculate",
                        "limit": 100,
                        "offset": 0,
                    },
                    "explanation": (
                        "Finds first 100 usages of 'calculate' (any type). Use offset for next page."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "FIND_USAGES_ERROR": {
                    "description": "General error during usage search",
                    "example": "Database error, invalid parameters, or corrupted data",
                    "solution": (
                        "Check database integrity, verify target_name and target_type parameters, "
                        "ensure project has been analyzed."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "target_name": "Target name that was searched",
                        "usages": (
                            "List of usage dictionaries from database. Each contains:\n"
                            "- file_id: Database ID of file\n"
                            "- line: Line number where usage occurs\n"
                            "- target_name: Name of target entity\n"
                            "- target_type: Type of target (method/property/class/function)\n"
                            "- target_class: Class name if target is method/property\n"
                            "- Additional database fields as available"
                        ),
                        "count": "Number of usages found",
                    },
                    "example": {
                        "success": True,
                        "target_name": "process_data",
                        "usages": [
                            {
                                "file_id": 1,
                                "line": 42,
                                "target_name": "process_data",
                                "target_type": "function",
                                "target_class": None,
                            },
                            {
                                "file_id": 2,
                                "line": 15,
                                "target_name": "process_data",
                                "target_type": "function",
                                "target_class": None,
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FIND_USAGES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Specify target_type to narrow search and improve performance",
                "Use target_class parameter when searching for methods/properties to avoid false matches",
                "Use limit and offset for pagination when dealing with many results",
                "Use file_path filter to focus on specific file",
                "Combine with find_dependencies for comprehensive usage tracking",
            ],
        }
