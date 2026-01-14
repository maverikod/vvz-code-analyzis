"""
MCP command wrapper: search_ast_nodes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class SearchASTNodesMCPCommand(BaseMCPCommand):
    """Search AST nodes across project/files."""

    name = "search_ast_nodes"
    version = "1.0.0"
    descr = "Search AST nodes (by type) in project files"
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
                "node_type": {
                    "type": "string",
                    "description": "AST node type to search (e.g., ClassDef, FunctionDef)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to limit search (absolute or relative)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 100,
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
        node_type: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 100,
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

            # Search AST nodes by type
            # We can search in classes, functions, methods tables
            # For more complex searches, would need to parse AST JSON
            results = []

            # Map node types to database tables
            if not node_type or node_type in ("ClassDef", "class"):
                # Search classes
                query = """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ?
                """
                params = [proj_id]

                if file_path:
                    from pathlib import Path

                    file_path_obj = Path(file_path)
                    root_path = Path(root_dir).resolve()
                    if file_path_obj.is_absolute():
                        try:
                            normalized_path = file_path_obj.relative_to(root_path)
                            file_path = str(normalized_path)
                        except ValueError:
                            pass
                    else:
                        file_path = str(file_path_obj)

                    file_record = db.get_file_by_path(file_path, proj_id)
                    if not file_record:
                        result = db.execute(
                            "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                            (proj_id, f"%{file_path}"),
                        )
                        data = result.get("data", [])
                        if data:
                            file_record = {"id": data[0]["id"]}

                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])

                query += " ORDER BY f.path, c.line"
                if limit:
                    query += f" LIMIT {limit}"

                result = db.execute(query, tuple(params))
                rows = result.get("data", [])
                for row in rows:
                    results.append(
                        {
                            "node_type": "ClassDef",
                            "name": row["name"],
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "docstring": row.get("docstring"),
                        }
                    )

            if not node_type or node_type in ("FunctionDef", "function"):
                # Search functions
                query = """
                    SELECT func.*, f.path as file_path
                    FROM functions func
                    JOIN files f ON func.file_id = f.id
                    WHERE f.project_id = ?
                """
                params = [proj_id]

                if file_path:
                    from pathlib import Path

                    file_path_obj = Path(file_path)
                    root_path = Path(root_dir).resolve()
                    if file_path_obj.is_absolute():
                        try:
                            normalized_path = file_path_obj.relative_to(root_path)
                            file_path = str(normalized_path)
                        except ValueError:
                            pass
                    else:
                        file_path = str(file_path_obj)

                    file_record = db.get_file_by_path(file_path, proj_id)
                    if not file_record:
                        result = db.execute(
                            "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                            (proj_id, f"%{file_path}"),
                        )
                        data = result.get("data", [])
                        if data:
                            file_record = {"id": data[0]["id"]}

                    if file_record:
                        query += " AND func.file_id = ?"
                        params.append(file_record["id"])

                query += " ORDER BY f.path, func.line"
                if limit:
                    query += f" LIMIT {limit}"

                result = db.execute(query, tuple(params))
                rows = result.get("data", [])
                for row in rows:
                    results.append(
                        {
                            "node_type": "FunctionDef",
                            "name": row["name"],
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "docstring": row.get("docstring"),
                        }
                    )

            if not node_type or node_type in ("method"):
                # Search methods
                query = """
                    SELECT m.*, c.name as class_name, f.path as file_path
                    FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ?
                """
                params = [proj_id]

                if file_path:
                    from pathlib import Path

                    file_path_obj = Path(file_path)
                    root_path = Path(root_dir).resolve()
                    if file_path_obj.is_absolute():
                        try:
                            normalized_path = file_path_obj.relative_to(root_path)
                            file_path = str(normalized_path)
                        except ValueError:
                            pass
                    else:
                        file_path = str(file_path_obj)

                    file_record = db.get_file_by_path(file_path, proj_id)
                    if not file_record:
                        result = db.execute(
                            "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                            (proj_id, f"%{file_path}"),
                        )
                        data = result.get("data", [])
                        if data:
                            file_record = {"id": data[0]["id"]}

                    if file_record:
                        query += " AND f.id = ?"
                        params.append(file_record["id"])

                query += " ORDER BY f.path, m.line"
                if limit:
                    query += f" LIMIT {limit}"

                result = db.execute(query, tuple(params))
                rows = result.get("data", [])
                for row in rows:
                    results.append(
                        {
                            "node_type": "FunctionDef",
                            "name": row["name"],
                            "class_name": row.get("class_name"),
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "docstring": row.get("docstring"),
                        }
                    )

            db.disconnect()

            return SuccessResult(
                data={
                    "success": True,
                    "node_type": node_type,
                    "nodes": results,
                    "count": len(results),
                }
            )
        except Exception as e:
            return self._handle_error(e, "SEARCH_AST_ERROR", "search_ast_nodes")

    @classmethod
    def metadata(cls: type["SearchASTNodesMCPCommand"]) -> Dict[str, Any]:
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
                "The search_ast_nodes command searches for AST nodes by type across project files. "
                "It maps AST node types to database tables (classes, functions, methods) and returns "
                "matching nodes with their locations and metadata.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Based on node_type, queries appropriate tables:\n"
                "   - 'ClassDef' or 'class': Searches classes table\n"
                "   - 'FunctionDef' or 'function': Searches functions table\n"
                "   - 'method': Searches methods table\n"
                "   - If node_type is null, searches all types\n"
                "5. If file_path provided, filters to nodes in that file\n"
                "6. Applies limit (default 100)\n"
                "7. Returns list of matching nodes with type, name, location, docstring\n\n"
                "Node Type Mapping:\n"
                "- 'ClassDef' or 'class': Maps to classes table\n"
                "- 'FunctionDef' or 'function': Maps to functions table\n"
                "- 'method': Maps to methods table\n"
                "- null: Searches all node types\n\n"
                "Use cases:\n"
                "- Find all classes in project\n"
                "- Find all functions in a file\n"
                "- Find all methods in project\n"
                "- Search for specific AST node types\n"
                "- Analyze code structure by node type\n\n"
                "Important notes:\n"
                "- Maps AST node types to database tables (not full AST traversal)\n"
                "- For full AST traversal, use get_ast and parse JSON\n"
                "- Default limit is 100 to prevent large result sets\n"
                "- Results include node_type, name, file_path, line, docstring"
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
                "node_type": {
                    "description": (
                        "AST node type to search for. Optional. Options: 'ClassDef', 'FunctionDef', "
                        "'class', 'function', 'method'. If null, searches all types. "
                        "Maps to database tables: ClassDef/class -> classes, FunctionDef/function -> functions, "
                        "method -> methods."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "ClassDef",
                        "FunctionDef",
                        "class",
                        "function",
                        "method",
                    ],
                },
                "file_path": {
                    "description": (
                        "Optional file path to limit search. If provided, only searches for nodes "
                        "in this specific file. Can be absolute or relative to root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
                "limit": {
                    "description": (
                        "Maximum number of results. Default is 100. Use to prevent large result sets."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 100,
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
                    "description": "Find all classes in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "node_type": "ClassDef",
                    },
                    "explanation": (
                        "Returns all classes in the project with their locations and metadata."
                    ),
                },
                {
                    "description": "Find all functions in a file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "node_type": "FunctionDef",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Returns all functions defined in src/main.py file."
                    ),
                },
                {
                    "description": "Find all methods in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "node_type": "method",
                        "limit": 200,
                    },
                    "explanation": ("Returns up to 200 methods in the project."),
                },
                {
                    "description": "Find all node types",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "limit": 500,
                    },
                    "explanation": (
                        "Returns up to 500 nodes of all types (classes, functions, methods) combined."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "SEARCH_AST_ERROR": {
                    "description": "General error during AST node search",
                    "example": "Database error, invalid parameters, or corrupted data",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project has been analyzed."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "node_type": "Node type that was searched (or null if all types)",
                        "nodes": (
                            "List of node dictionaries. Each contains:\n"
                            "- node_type: AST node type ('ClassDef' or 'FunctionDef')\n"
                            "- name: Node name (class/function/method name)\n"
                            "- file_path: File where node is defined\n"
                            "- line: Line number where node is defined\n"
                            "- docstring: Node docstring (if available)\n"
                            "- class_name: Class name (for methods only)"
                        ),
                        "count": "Number of nodes found",
                    },
                    "example": {
                        "success": True,
                        "node_type": "ClassDef",
                        "nodes": [
                            {
                                "node_type": "ClassDef",
                                "name": "DataProcessor",
                                "file_path": "src/processor.py",
                                "line": 10,
                                "docstring": "Processes data files.",
                            },
                            {
                                "node_type": "ClassDef",
                                "name": "TaskHandler",
                                "file_path": "src/handlers.py",
                                "line": 20,
                                "docstring": "Handles tasks.",
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, SEARCH_AST_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use node_type to filter specific node types for better performance",
                "Use file_path filter to focus on specific file",
                "Set appropriate limit to prevent large result sets",
                "Note: This searches database tables, not full AST. Use get_ast for full AST traversal",
                "Combine with list_code_entities for comprehensive entity listing",
            ],
        }
