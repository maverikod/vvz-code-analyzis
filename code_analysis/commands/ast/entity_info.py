"""
MCP command wrapper: get_code_entity_info.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetCodeEntityInfoMCPCommand(BaseMCPCommand):
    """Get detailed information about a code entity (class, function, method)."""

    name = "get_code_entity_info"
    version = "1.0.0"
    descr = "Get detailed information about a class, function, or method"
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', or 'method'",
                    "enum": ["class", "function", "method"],
                },
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to search in (relative to project root)",
                },
                "line": {
                    "type": "integer",
                    "description": "Optional line number for disambiguation",
                },
            },
            "required": ["project_id", "entity_type", "entity_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        entity_type: str,
        entity_name: str,
        file_path: Optional[str] = None,
        line: Optional[int] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._resolve_project_root(project_id)
            db = self._open_database()
            proj_id = project_id

            # Get entity info from database
            query = None
            params = []

            if entity_type == "class":
                query = "SELECT c.*, f.path as file_path FROM classes c JOIN files f ON c.file_id = f.id WHERE c.name = ? AND f.project_id = ?"
                params = [entity_name, proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                if line:
                    query += " AND c.line = ?"
                    params.append(line)
            elif entity_type == "function":
                query = "SELECT func.*, f.path as file_path FROM functions func JOIN files f ON func.file_id = f.id WHERE func.name = ? AND f.project_id = ?"
                params = [entity_name, proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND func.file_id = ?"
                        params.append(file_record["id"])
                if line:
                    query += " AND func.line = ?"
                    params.append(line)
            elif entity_type == "method":
                query = "SELECT m.*, c.name as class_name, f.path as file_path FROM methods m JOIN classes c ON m.class_id = c.id JOIN files f ON c.file_id = f.id WHERE m.name = ? AND f.project_id = ?"
                params = [entity_name, proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                if line:
                    query += " AND m.line = ?"
                    params.append(line)
            else:
                db.disconnect()
                return ErrorResult(
                    message=f"Unknown entity type: {entity_type}",
                    code="INVALID_ENTITY_TYPE",
                )

            result = db.execute(query, tuple(params))
            rows = result.get("data", [])
            db.disconnect()

            if rows:
                entities = rows
                return SuccessResult(
                    data={
                        "success": True,
                        "entity_type": entity_type,
                        "entity_name": entity_name,
                        "entities": entities,
                        "count": len(entities),
                    }
                )
            return ErrorResult(
                message=f"Entity not found: {entity_type} {entity_name}",
                code="ENTITY_NOT_FOUND",
            )
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_INFO_ERROR", "get_code_entity_info"
            )

    @classmethod
    def metadata(cls: type["GetCodeEntityInfoMCPCommand"]) -> Dict[str, Any]:
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
                "The get_code_entity_info command retrieves detailed information about a code entity "
                "(class, function, or method) from the analysis database. It returns complete metadata "
                "including location, docstrings, signatures, and other attributes.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Based on entity_type, queries appropriate table:\n"
                "   - 'class': Queries classes table\n"
                "   - 'function': Queries functions table\n"
                "   - 'method': Queries methods table (with class join)\n"
                "5. Filters by entity_name (required)\n"
                "6. If file_path provided, filters to that file\n"
                "7. If line provided, filters to that line number (for disambiguation)\n"
                "8. Returns all matching entities with full metadata\n\n"
                "Entity Types:\n"
                "- class: Returns class information including bases, docstring, file location\n"
                "- function: Returns function information including parameters, docstring, file location\n"
                "- method: Returns method information including class context, parameters, docstring\n\n"
                "Use cases:\n"
                "- Get detailed information about a specific entity\n"
                "- Inspect entity signatures and docstrings\n"
                "- Find entity location (file and line)\n"
                "- Disambiguate entities with same name\n"
                "- Code navigation and documentation\n\n"
                "Important notes:\n"
                "- Returns all matching entities (may be multiple if same name in different files)\n"
                "- Use file_path and line parameters to disambiguate\n"
                "- For methods, includes class_name in results\n"
                "- Returns full database record with all available fields"
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
                        "Type of entity to retrieve. Required. Options: 'class', 'function', 'method'. "
                        "Determines which database table to query."
                    ),
                    "type": "string",
                    "required": True,
                    "enum": ["class", "function", "method"],
                },
                "entity_name": {
                    "description": (
                        "Name of the entity to retrieve. Required. "
                        "Must match exactly (case-sensitive)."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["DataProcessor", "process_data", "execute"],
                },
                "file_path": {
                    "description": (
                        "Optional file path to filter by. If provided, only searches for entities "
                        "in this specific file. Can be absolute or relative to root_dir. "
                        "Useful for disambiguation when same name exists in multiple files."
                    ),
                    "type": "string",
                    "required": False,
                },
                "line": {
                    "description": (
                        "Optional line number for disambiguation. If provided, only returns entity "
                        "at this specific line number. Use with file_path for precise matching."
                    ),
                    "type": "integer",
                    "required": False,
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
                    "description": "Get information about a class",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "class",
                        "entity_name": "DataProcessor",
                    },
                    "explanation": (
                        "Retrieves detailed information about DataProcessor class, including "
                        "location, bases, docstring, and other attributes."
                    ),
                },
                {
                    "description": "Get information about a function",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                        "entity_name": "process_data",
                    },
                    "explanation": (
                        "Retrieves detailed information about process_data function, including "
                        "parameters, docstring, and file location."
                    ),
                },
                {
                    "description": "Get method information with file filter",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "method",
                        "entity_name": "execute",
                        "file_path": "src/handlers.py",
                    },
                    "explanation": (
                        "Retrieves execute method information from src/handlers.py file only. "
                        "Useful when multiple classes have methods with same name."
                    ),
                },
                {
                    "description": "Disambiguate with line number",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                        "entity_name": "helper",
                        "file_path": "src/utils.py",
                        "line": 42,
                    },
                    "explanation": (
                        "Retrieves helper function at line 42 in src/utils.py. "
                        "Useful when file has multiple functions with same name."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "INVALID_ENTITY_TYPE": {
                    "description": "Invalid entity_type parameter",
                    "example": "entity_type='invalid' (not class/function/method)",
                    "solution": "Use one of: 'class', 'function', 'method'",
                },
                "ENTITY_NOT_FOUND": {
                    "description": "Entity not found in database",
                    "example": "entity_name='NonExistent' but entity doesn't exist",
                    "solution": (
                        "Verify entity name is correct (case-sensitive). Check that entity exists "
                        "and has been indexed. Run update_indexes to index entities."
                    ),
                },
                "GET_ENTITY_INFO_ERROR": {
                    "description": "General error during entity info retrieval",
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
                        "entity_type": "Entity type that was searched",
                        "entity_name": "Entity name that was searched",
                        "entities": (
                            "List of entity dictionaries from database. Each contains:\n"
                            "- For classes: name, file_path, line, bases, docstring, and other class fields\n"
                            "- For functions: name, file_path, line, parameters, docstring, and other function fields\n"
                            "- For methods: name, class_name, file_path, line, parameters, docstring, and other method fields\n"
                            "- All database fields are included"
                        ),
                        "count": "Number of matching entities found",
                    },
                    "example_class": {
                        "success": True,
                        "entity_type": "class",
                        "entity_name": "DataProcessor",
                        "entities": [
                            {
                                "name": "DataProcessor",
                                "file_path": "src/processor.py",
                                "line": 10,
                                "bases": '["BaseProcessor"]',
                                "docstring": "Processes data files.",
                            }
                        ],
                        "count": 1,
                    },
                    "example_function": {
                        "success": True,
                        "entity_type": "function",
                        "entity_name": "process_data",
                        "entities": [
                            {
                                "name": "process_data",
                                "file_path": "src/utils.py",
                                "line": 42,
                                "parameters": "data, count",
                                "docstring": "Process data with count.",
                            }
                        ],
                        "count": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, INVALID_ENTITY_TYPE, ENTITY_NOT_FOUND, GET_ENTITY_INFO_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use file_path parameter to disambiguate entities with same name",
                "Use line parameter for precise matching when multiple entities exist",
                "Check count field to see if multiple matches found",
                "Combine with find_usages to get complete entity information",
                "Use for code navigation and documentation generation",
            ],
        }
