"""
MCP command wrapper: list_code_entities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ListCodeEntitiesMCPCommand(BaseMCPCommand):
    """List code entities (classes, functions, methods) in a file or project."""

    name = "list_code_entities"
    version = "1.0.0"
    descr = "List classes, functions, or methods in a file or project"
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
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', 'method', or null for all",
                    "enum": ["class", "function", "method"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
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
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_type: Optional[str] = None,
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

            # List entities from database
            entities = []
            
            if not entity_type or entity_type == "class":
                query = "SELECT c.*, f.path as file_path FROM classes c JOIN files f ON c.file_id = f.id WHERE f.project_id = ?"
                params = [proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                query += " ORDER BY f.path, c.line"
                if limit:
                    query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    entities.append({"type": "class", **row})
            
            if not entity_type or entity_type == "function":
                query = "SELECT func.*, f.path as file_path FROM functions func JOIN files f ON func.file_id = f.id WHERE f.project_id = ?"
                params = [proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND func.file_id = ?"
                        params.append(file_record["id"])
                query += " ORDER BY f.path, func.line"
                if limit:
                    query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    entities.append({"type": "function", **row})
            
            if not entity_type or entity_type == "method":
                query = "SELECT m.*, c.name as class_name, f.path as file_path FROM methods m JOIN classes c ON m.class_id = c.id JOIN files f ON c.file_id = f.id WHERE f.project_id = ?"
                params = [proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                query += " ORDER BY f.path, m.line"
                if limit:
                    query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    entities.append({"type": "method", **row})
            
            db.disconnect()
            
            return SuccessResult(
                data={
                    "success": True,
                    "entities": entities,
                    "count": len(entities),
                }
            )
        except Exception as e:
            return self._handle_error(e, "LIST_ENTITIES_ERROR", "list_code_entities")

    @classmethod
    def metadata(cls: type["ListCodeEntitiesMCPCommand"]) -> Dict[str, Any]:
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
                "The list_code_entities command lists all code entities (classes, functions, methods) "
                "in a file or project. It provides a comprehensive catalog of all code entities with "
                "their locations and metadata.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Based on entity_type, queries appropriate tables:\n"
                "   - If entity_type is null or 'class': Queries classes table\n"
                "   - If entity_type is null or 'function': Queries functions table\n"
                "   - If entity_type is null or 'method': Queries methods table (with class join)\n"
                "5. If file_path provided, filters to entities in that file\n"
                "6. Applies pagination: limit and offset\n"
                "7. Combines results from all entity types (if entity_type is null)\n"
                "8. Returns list of entities with type indicator\n\n"
                "Entity Types:\n"
                "- 'class': Lists all classes with name, file_path, line, bases, docstring\n"
                "- 'function': Lists all functions with name, file_path, line, parameters, docstring\n"
                "- 'method': Lists all methods with name, class_name, file_path, line, parameters, docstring\n"
                "- null: Lists all entity types combined\n\n"
                "Use cases:\n"
                "- Get catalog of all classes in project\n"
                "- List all functions in a file\n"
                "- Find all methods in a class\n"
                "- Generate code documentation\n"
                "- Analyze code structure\n\n"
                "Important notes:\n"
                "- If entity_type is null, returns all types combined\n"
                "- Each entity includes 'type' field indicating its type\n"
                "- Results ordered by file_path and line number\n"
                "- Supports pagination with limit and offset"
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
                "entity_type": {
                    "description": (
                        "Type of entity to list. Optional. If null, lists all types. "
                        "Options: 'class', 'function', 'method'. "
                        "If null, returns combined list of all entity types."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["class", "function", "method"],
                },
                "file_path": {
                    "description": (
                        "Optional file path to filter by. If provided, only lists entities "
                        "from this specific file. Can be absolute or relative to root_dir."
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
                    "description": "List all classes in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "class",
                    },
                    "explanation": (
                        "Returns list of all classes in the project with their locations and metadata."
                    ),
                },
                {
                    "description": "List all entities in a file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Returns all classes, functions, and methods defined in src/main.py."
                    ),
                },
                {
                    "description": "List all functions in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                    },
                    "explanation": (
                        "Returns list of all functions in the project."
                    ),
                },
                {
                    "description": "List entities with pagination",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "method",
                        "limit": 50,
                        "offset": 0,
                    },
                    "explanation": (
                        "Returns first 50 methods. Use offset for next page."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "LIST_ENTITIES_ERROR": {
                    "description": "General error during entity listing",
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
                        "entities": (
                            "List of entity dictionaries. Each entity includes:\n"
                            "- type: Entity type ('class', 'function', or 'method')\n"
                            "- For classes: name, file_path, line, bases, docstring, and other class fields\n"
                            "- For functions: name, file_path, line, parameters, docstring, and other function fields\n"
                            "- For methods: name, class_name, file_path, line, parameters, docstring, and other method fields\n"
                            "- All database fields are included"
                        ),
                        "count": "Number of entities found",
                    },
                    "example": {
                        "success": True,
                        "entities": [
                            {
                                "type": "class",
                                "name": "DataProcessor",
                                "file_path": "src/processor.py",
                                "line": 10,
                                "bases": '["BaseProcessor"]',
                                "docstring": "Processes data.",
                            },
                            {
                                "type": "function",
                                "name": "process_data",
                                "file_path": "src/utils.py",
                                "line": 42,
                                "parameters": "data, count",
                                "docstring": "Process data.",
                            },
                            {
                                "type": "method",
                                "name": "execute",
                                "class_name": "TaskHandler",
                                "file_path": "src/handlers.py",
                                "line": 20,
                                "parameters": "self, task",
                                "docstring": "Execute task.",
                            },
                        ],
                        "count": 3,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, LIST_ENTITIES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use entity_type to filter specific entity types for better performance",
                "Use file_path filter to focus on specific file",
                "Use limit and offset for pagination with large result sets",
                "Check 'type' field in results when entity_type is null",
                "Combine with get_code_entity_info for detailed entity information",
            ],
        }
