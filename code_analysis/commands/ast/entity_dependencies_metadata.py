"""
Metadata for get_entity_dependencies and get_entity_dependents MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict

from .entity_dependencies_helpers import CALLEE_TYPES, CALLER_TYPES


def get_entity_dependencies_metadata() -> Dict[str, Any]:
    """Return full metadata dict for get_entity_dependencies command."""
    return {
        "name": "get_entity_dependencies",
        "version": "1.0.0",
        "description": (
            "Get list of entities that the given entity depends on (by entity type and id)"
        ),
        "category": "ast",
        "author": "Vasiliy Zdanovskiy",
        "email": "vasilyvz@gmail.com",
        "parameters_summary": (
            "Required: project_id, entity_type. Optional: entity_id, entity_name, target_class. "
            "No limit parameter; provide either entity_id or entity_name."
        ),
        "detailed_description": (
            "The get_entity_dependencies command returns the list of entities that a given "
            "entity depends on (what it calls or uses), using the entity cross-reference table. "
            "You can call it with entity_name + entity_type (resolved to id in the project) or with entity_id.\n\n"
            "Operation flow:\n"
            "1. Validates root_dir exists and is a directory\n"
            "2. Opens database connection via proxy\n"
            "3. Resolves project_id (from parameter or inferred from root_dir)\n"
            "4. If entity_name given, resolves entity_name + entity_type to entity_id in the project; "
            "if entity_id given, uses it\n"
            "5. Queries entity_cross_ref table by caller_* column (class_id, method_id, or function_id)\n"
            "6. Resolves file_id to file_path and cst_node_id via JOIN with classes/methods/functions\n"
            "7. Returns list of callee entities with type, id, ref_type, file_path, line, cst_node_id (only valid UUID4)\n\n"
            "Data source: entity_cross_ref table; ref_type: 'call', 'instantiation', 'attribute', 'inherit'. "
            "Use entity_name + entity_type when you have the name from code. Use entity_id when you have the id. "
            "Run update_indexes after code changes to refresh."
        ),
        "parameters": {
            "root_dir": {
                "description": "Project root directory path.",
                "type": "string",
                "required": True,
            },
            "entity_type": {
                "description": "Type: 'class', 'method', or 'function'.",
                "type": "string",
                "required": True,
                "enum": list(CALLER_TYPES),
            },
            "entity_id": {
                "description": (
                    "Primary key of the entity (UUID string after DB UUID migration). "
                    "Legacy integer row ids may still work until migration completes."
                ),
                "type": "string",
                "required": False,
                "examples": [
                    "a1b2c3d4-e5f6-4789-a012-345678901234",
                    "b2c3d4e5-f6a7-4890-b123-456789012345",
                ],
            },
            "entity_name": {
                "description": "Name of the entity; resolved to id within project.",
                "type": "string",
                "required": False,
            },
            "target_class": {
                "description": "Optional class name when entity_type is 'method'.",
                "type": "string",
                "required": False,
            },
            "project_id": {
                "description": "Optional project UUID.",
                "type": "string",
                "required": False,
            },
        },
        "usage_examples": [
            {
                "description": "Get dependencies of a function by id",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "entity_type": "function",
                    "entity_id": "a1b2c3d4-e5f6-4789-a012-345678901234",
                },
                "explanation": (
                    "Returns all entities that the given function (by UUID pk) calls or uses."
                ),
            },
            {
                "description": "Get dependencies by name",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "entity_type": "function",
                    "entity_name": "process_data",
                },
                "explanation": "Resolves 'process_data' to id, then returns what that function calls.",
            },
        ],
        "error_cases": {
            "PROJECT_NOT_FOUND": {
                "description": "Project not found in database",
                "solution": "Register project and run update_indexes first.",
            },
            "VALIDATION_ERROR": {
                "description": "Invalid entity_type or neither entity_id nor entity_name provided",
                "solution": "Use 'class', 'method', or 'function'; provide entity_id or entity_name.",
            },
            "ENTITY_NOT_FOUND": {
                "description": "Entity name not found in project",
                "solution": "Check spelling and that the project has been indexed.",
            },
            "GET_ENTITY_DEPENDENCIES_ERROR": {
                "description": "General error during query",
                "solution": "Check database integrity and proxy connection.",
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully",
                "data": {
                    "dependencies": (
                        "List of dicts: callee_entity_type, callee_entity_id (UUID string pk), "
                        "ref_type, file_path, line, cst_node_id."
                    ),
                },
            },
            "error": {
                "description": "Command failed",
                "code": "PROJECT_NOT_FOUND | VALIDATION_ERROR | ENTITY_NOT_FOUND | GET_ENTITY_DEPENDENCIES_ERROR",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use entity_name + entity_type when you know the name from code (no need to resolve id first)",
            "Use get_entity_dependents to find who depends on an entity (reverse direction)",
            "Run update_indexes after code changes so entity_cross_ref is up to date",
        ],
    }


def get_entity_dependents_metadata() -> Dict[str, Any]:
    """Return full metadata dict for get_entity_dependents command."""
    return {
        "name": "get_entity_dependents",
        "version": "1.0.0",
        "description": (
            "Get list of entities that depend on the given entity (by entity type and id)"
        ),
        "category": "ast",
        "author": "Vasiliy Zdanovskiy",
        "email": "vasilyvz@gmail.com",
        "parameters_summary": (
            "Required: project_id, entity_type. Optional: entity_id, entity_name, target_class. "
            "No limit parameter; provide either entity_id or entity_name."
        ),
        "detailed_description": (
            "The get_entity_dependents command returns the list of entities that depend on "
            "a given entity (what calls or uses it), using the entity cross-reference table. "
            "You can call it with entity_name + entity_type (resolved to id in the project) or with entity_id.\n\n"
            "Operation flow:\n"
            "1. Validates root_dir, opens database\n"
            "2. Resolves project_id; if entity_name given, resolves to entity_id\n"
            "3. Queries entity_cross_ref by callee_* column\n"
            "4. Returns list of caller entities with type, id, ref_type, file_path, line, cst_node_id (valid UUID4)\n\n"
            "Use for impact analysis before renaming or deleting. Run update_indexes after code changes."
        ),
        "parameters": {
            "root_dir": {
                "description": "Project root directory path.",
                "type": "string",
                "required": True,
            },
            "entity_type": {
                "description": "Type: 'class', 'method', or 'function'.",
                "type": "string",
                "required": True,
                "enum": list(CALLEE_TYPES),
            },
            "entity_id": {
                "description": (
                    "Primary key of the entity (UUID string after DB UUID migration). "
                    "Legacy integer row ids may still work until migration completes."
                ),
                "type": "string",
                "required": False,
                "examples": [
                    "a1b2c3d4-e5f6-4789-a012-345678901234",
                    "b2c3d4e5-f6a7-4890-b123-456789012345",
                ],
            },
            "entity_name": {
                "description": "Name of the entity; resolved to id within project.",
                "type": "string",
                "required": False,
            },
            "target_class": {
                "description": "Optional class name when entity_type is 'method'.",
                "type": "string",
                "required": False,
            },
            "project_id": {
                "description": "Optional project UUID.",
                "type": "string",
                "required": False,
            },
        },
        "usage_examples": [
            {
                "description": "Get dependents of a function by id",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "entity_type": "function",
                    "entity_id": "a1b2c3d4-e5f6-4789-a012-345678901234",
                },
                "explanation": (
                    "Returns all entities that call the function identified by UUID pk."
                ),
            },
            {
                "description": "Get dependents by name",
                "command": {
                    "root_dir": "/home/user/projects/my_project",
                    "entity_type": "function",
                    "entity_name": "process_data",
                },
                "explanation": "Resolves 'process_data' to id, then returns who calls it.",
            },
        ],
        "error_cases": {
            "PROJECT_NOT_FOUND": {
                "description": "Project not found in database",
                "solution": "Register project and run update_indexes first.",
            },
            "VALIDATION_ERROR": {
                "description": "Invalid entity_type or neither entity_id nor entity_name provided",
                "solution": "Use 'class', 'method', or 'function'; provide entity_id or entity_name.",
            },
            "ENTITY_NOT_FOUND": {
                "description": "Entity name not found in project",
                "solution": "Check spelling and that the project has been indexed.",
            },
            "GET_ENTITY_DEPENDENTS_ERROR": {
                "description": "General error during query",
                "solution": "Check database integrity and proxy connection.",
            },
        },
        "return_value": {
            "success": {
                "description": "Command executed successfully",
                "data": {
                    "dependents": (
                        "List of dicts: caller_entity_type, caller_entity_id (UUID string pk), "
                        "ref_type, file_path, line, cst_node_id."
                    ),
                },
            },
            "error": {
                "description": "Command failed",
                "code": "PROJECT_NOT_FOUND | VALIDATION_ERROR | ENTITY_NOT_FOUND | GET_ENTITY_DEPENDENTS_ERROR",
                "message": "Human-readable error message",
            },
        },
        "best_practices": [
            "Use entity_name + entity_type when you know the name from code",
            "Use get_entity_dependencies to find what an entity depends on (reverse direction)",
            "Run update_indexes after code changes so entity_cross_ref is up to date",
            "Use for impact analysis before refactoring or deleting an entity",
        ],
    }
