"""
MCP command wrapper: list_code_entities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .file_resolution import resolve_project_file_record
from .list_entities_page import count_code_entities, fetch_code_entities_page
from ..base_mcp_command import BaseMCPCommand
from ...core.exceptions import ValidationError
from ...core.list_pagination import (
    build_list_page_payload,
    list_pagination_schema_properties,
    resolve_list_pagination,
)
from ...core.uuid_validation import is_valid_uuid4 as _is_valid_uuid4


class ListCodeEntitiesMCPCommand(BaseMCPCommand):
    """List code entities (classes, functions, methods) in a file or project."""

    name = "list_code_entities"
    version = "1.1.0"
    descr = (
        "List classes, functions, or methods in a file or project. "
        "Returns paginated ``items`` (default ``page_size`` 20); use "
        "``block_position`` for the next page."
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        base_props = cls._get_base_schema_properties()
        pagination = list_pagination_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', 'method', or null for all",
                    "enum": ["class", "function", "method"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (relative to project root)",
                },
                **pagination,
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        entity_type: Optional[str] = None,
        file_path: Optional[str] = None,
        page_size: Optional[int] = None,
        block_position: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        **kwargs,
    ) -> SuccessResult:
        """Execute the command."""
        params: Dict[str, Any] = {
            "project_id": project_id,
            "entity_type": entity_type,
            "file_path": file_path,
            "page_size": page_size,
            "block_position": block_position,
            "limit": limit,
            "offset": offset,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "list_code_entities")
        project_id = params["project_id"]
        entity_type = params.get("entity_type")
        file_path = params.get("file_path")
        page_size, offset, block_position = resolve_list_pagination(params)

        try:
            root_path = self._resolve_project_root(project_id)
            db = self._open_database()
            proj_id = project_id

            resolved_file_id: Optional[Any] = None
            if file_path:
                resolution = resolve_project_file_record(
                    db=db,
                    project_id=proj_id,
                    project_root=root_path,
                    file_path=file_path,
                )
                file_record = resolution["file_record"]
                if not file_record:
                    db.disconnect()
                    return SuccessResult(
                        data=build_list_page_payload(
                            items=[],
                            total=0,
                            page_size=page_size,
                            block_position=block_position,
                            offset=offset,
                            legacy_items_key="entities",
                        )
                    )
                resolved_file_id = file_record["id"]

            total = count_code_entities(
                db,
                project_id=proj_id,
                entity_type=entity_type,
                file_id=resolved_file_id,
            )
            entities = fetch_code_entities_page(
                db,
                project_id=proj_id,
                entity_type=entity_type,
                file_id=resolved_file_id,
                limit=page_size,
                offset=offset,
            )
            db.disconnect()

            return SuccessResult(
                data=build_list_page_payload(
                    items=entities,
                    total=total,
                    page_size=page_size,
                    block_position=block_position,
                    offset=offset,
                    legacy_items_key="entities",
                )
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
                    "explanation": ("Returns list of all functions in the project."),
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
                            "- id: Database primary key of the entity row (UUID string after DB UUID migration)\n"
                            "- file_id: Foreign key to files.id (UUID string after migration)\n"
                            "- file_path: Path relative to project root (required)\n"
                            "- cst_node_id: Valid UUID4 CST node identifier (required, non-empty)\n"
                            "- type: Entity type ('class', 'function', or 'method')\n"
                            "- For classes: name, line, bases, docstring, and other class fields\n"
                            "- For functions: name, line, parameters, docstring, and other function fields\n"
                            "- For methods: name, class_name, line, parameters, docstring, and other method fields\n"
                            "- Only entities with persisted cst_node_id are returned; no fallback to line-only identity"
                        ),
                        "count": "Number of entities found",
                    },
                    "example": {
                        "success": True,
                        "entities": [
                            {
                                "type": "class",
                                "id": "11111111-2222-4333-8444-555566667777",
                                "file_id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
                                "name": "DataProcessor",
                                "file_path": "src/processor.py",
                                "cst_node_id": "a1b2c3d4-e5f6-4789-a012-345678901234",
                                "line": 10,
                                "bases": '["BaseProcessor"]',
                                "docstring": "Processes data.",
                            },
                            {
                                "type": "function",
                                "id": "22222222-3333-4444-8555-666677778888",
                                "file_id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
                                "name": "process_data",
                                "file_path": "src/utils.py",
                                "cst_node_id": "b2c3d4e5-f6a7-4890-b123-456789012345",
                                "line": 42,
                                "parameters": "data, count",
                                "docstring": "Process data.",
                            },
                            {
                                "type": "method",
                                "id": "33333333-4444-4555-8666-777788889999",
                                "file_id": "bbbbbbbb-cccc-4ddd-eeee-ffffffffffff",
                                "name": "execute",
                                "class_name": "TaskHandler",
                                "file_path": "src/handlers.py",
                                "cst_node_id": "c3d4e5f6-a7b8-4901-c234-567890123456",
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
