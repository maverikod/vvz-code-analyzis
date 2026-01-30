"""
MCP commands: get_entity_dependencies, get_entity_dependents.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand

CALLER_TYPES = ("class", "method", "function")
CALLEE_TYPES = ("class", "method", "function")


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert sqlite Row or dict to dict."""
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def _get_entity_dependencies_via_execute(
    db: Any, entity_type: str, entity_id: int
) -> List[Dict[str, Any]]:
    """Get dependencies by querying entity_cross_ref via execute()."""
    if entity_type == "class":
        col = "caller_class_id"
    elif entity_type == "method":
        col = "caller_method_id"
    elif entity_type == "function":
        col = "caller_function_id"
    else:
        return []

    sql = f"""
        SELECT callee_class_id, callee_method_id, callee_function_id,
               ref_type, file_id, line
        FROM entity_cross_ref
        WHERE {col} = ?
    """
    result = db.execute(sql, (entity_id,))
    rows = result.get("data") or []
    if not rows:
        return []

    file_ids = list(
        {_row_to_dict(r).get("file_id") for r in rows if _row_to_dict(r).get("file_id")}
    )
    path_by_id: Dict[Optional[int], str] = {}
    if file_ids:
        placeholders = ",".join("?" * len(file_ids))
        path_result = db.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders})",
            tuple(file_ids),
        )
        path_rows = path_result.get("data") or []
        for r in path_rows:
            d = _row_to_dict(r)
            path_by_id[d["id"]] = d.get("path", "")

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = _row_to_dict(r)
        if d.get("callee_class_id") is not None:
            callee_type, callee_id = "class", d["callee_class_id"]
        elif d.get("callee_method_id") is not None:
            callee_type, callee_id = "method", d["callee_method_id"]
        else:
            callee_type, callee_id = "function", d["callee_function_id"]
        file_id = d.get("file_id")
        out.append(
            {
                "callee_entity_type": callee_type,
                "callee_entity_id": callee_id,
                "ref_type": d.get("ref_type", ""),
                "file_path": path_by_id.get(file_id, ""),
                "line": d.get("line"),
            }
        )
    return out


def _resolve_entity_id_by_name(
    db: Any,
    project_id: str,
    entity_type: str,
    entity_name: str,
    target_class: Optional[str] = None,
) -> Optional[int]:
    """
    Resolve entity name to database id within the project.
    Returns first match (by file path order); for methods, target_class disambiguates.
    """
    if entity_type == "class":
        r = db.execute(
            """
            SELECT c.id FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND c.name = ?
            ORDER BY f.path LIMIT 1
            """,
            (project_id, entity_name),
        )
    elif entity_type == "function":
        r = db.execute(
            """
            SELECT fn.id FROM functions fn
            JOIN files f ON fn.file_id = f.id
            WHERE f.project_id = ? AND fn.name = ?
            ORDER BY f.path LIMIT 1
            """,
            (project_id, entity_name),
        )
    elif entity_type == "method":
        if target_class:
            r = db.execute(
                """
                SELECT m.id FROM methods m
                JOIN classes c ON m.class_id = c.id
                JOIN files f ON c.file_id = f.id
                WHERE f.project_id = ? AND c.name = ? AND m.name = ?
                ORDER BY f.path LIMIT 1
                """,
                (project_id, target_class, entity_name),
            )
        else:
            r = db.execute(
                """
                SELECT m.id FROM methods m
                JOIN classes c ON m.class_id = c.id
                JOIN files f ON c.file_id = f.id
                WHERE f.project_id = ? AND m.name = ?
                ORDER BY f.path LIMIT 1
                """,
                (project_id, entity_name),
            )
    else:
        return None
    rows = r.get("data") or []
    if not rows:
        return None
    return _row_to_dict(rows[0]).get("id")


def _get_entity_dependents_via_execute(
    db: Any, entity_type: str, entity_id: int
) -> List[Dict[str, Any]]:
    """Get dependents by querying entity_cross_ref via execute()."""
    if entity_type == "class":
        col = "callee_class_id"
    elif entity_type == "method":
        col = "callee_method_id"
    elif entity_type == "function":
        col = "callee_function_id"
    else:
        return []

    sql = f"""
        SELECT caller_class_id, caller_method_id, caller_function_id,
               ref_type, file_id, line
        FROM entity_cross_ref
        WHERE {col} = ?
    """
    result = db.execute(sql, (entity_id,))
    rows = result.get("data") or []
    if not rows:
        return []

    file_ids = list(
        {_row_to_dict(r).get("file_id") for r in rows if _row_to_dict(r).get("file_id")}
    )
    path_by_id: Dict[Optional[int], str] = {}
    if file_ids:
        placeholders = ",".join("?" * len(file_ids))
        path_result = db.execute(
            f"SELECT id, path FROM files WHERE id IN ({placeholders})",
            tuple(file_ids),
        )
        path_rows = path_result.get("data") or []
        for r in path_rows:
            d = _row_to_dict(r)
            path_by_id[d["id"]] = d.get("path", "")

    out = []
    for r in rows:
        d = _row_to_dict(r)
        if d.get("caller_class_id") is not None:
            caller_type, caller_id = "class", d["caller_class_id"]
        elif d.get("caller_method_id") is not None:
            caller_type, caller_id = "method", d["caller_method_id"]
        else:
            caller_type, caller_id = "function", d["caller_function_id"]
        file_id = d.get("file_id")
        out.append(
            {
                "caller_entity_type": caller_type,
                "caller_entity_id": caller_id,
                "ref_type": d.get("ref_type", ""),
                "file_path": path_by_id.get(file_id, ""),
                "line": d.get("line"),
            }
        )
    return out


class GetEntityDependenciesMCPCommand(BaseMCPCommand):
    """Get dependencies of an entity (what it calls/uses) by entity id."""

    name = "get_entity_dependencies"
    version = "1.0.0"
    descr = (
        "Get list of entities that the given entity depends on (by entity type and id)"
    )
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
                    "description": (
                        "Project root directory (contains data/code_analysis.db). "
                        "Can be absolute or relative."
                    ),
                },
                "entity_type": {
                    "type": "string",
                    "description": (
                        "Type of the entity: 'class', 'method', or 'function'. "
                        "Required when using entity_name."
                    ),
                    "enum": list(CALLER_TYPES),
                },
                "entity_id": {
                    "type": "integer",
                    "description": (
                        "Database ID of the entity. Either entity_id or entity_name must be set. "
                        "Use entity_name when the caller knows only the name (e.g. from code)."
                    ),
                },
                "entity_name": {
                    "type": "string",
                    "description": (
                        "Name of the entity. Resolved to id within the project. "
                        "Either entity_id or entity_name must be set. Use with entity_type; "
                        "for methods, optionally set target_class to disambiguate."
                    ),
                },
                "target_class": {
                    "type": "string",
                    "description": (
                        "Optional class name when entity_type is 'method' and entity_name is used."
                    ),
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional project UUID; if omitted, inferred by root_dir."
                    ),
                },
            },
            "required": ["root_dir", "entity_type"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        entity_name: Optional[str] = None,
        target_class: Optional[str] = None,
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
            if entity_type not in CALLER_TYPES:
                return ErrorResult(
                    message=f"entity_type must be one of {CALLER_TYPES!r}",
                    code="VALIDATION_ERROR",
                )
            eid = entity_id
            if eid is None:
                if not entity_name:
                    return ErrorResult(
                        message="Provide entity_id or entity_name",
                        code="VALIDATION_ERROR",
                    )
                eid = _resolve_entity_id_by_name(
                    db, proj_id, entity_type, entity_name, target_class
                )
                if eid is None:
                    return ErrorResult(
                        message=f"Entity not found: {entity_type!r} {entity_name!r}",
                        code="ENTITY_NOT_FOUND",
                    )
            deps = _get_entity_dependencies_via_execute(db, entity_type, eid)
            return SuccessResult(data={"dependencies": deps})
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_DEPENDENCIES_ERROR", "get_entity_dependencies"
            )

    @classmethod
    def metadata(cls: type["GetEntityDependenciesMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Provides comprehensive information including descriptions,
        usage examples, and edge cases. Detail level not less than one page.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
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
                "6. Resolves file_id to file_path for each row\n"
                "7. Returns list of callee entities with type, id, ref_type, file_path, line\n\n"
                "Data source:\n"
                "- The entity_cross_ref table is populated during update_file_data_atomic (and update_indexes) "
                "when usages are tracked. Each row links a caller entity (class/method/function) to a callee "
                "entity. ref_type can be 'call', 'instantiation', 'attribute', 'inherit'.\n\n"
                "Use cases:\n"
                "- Get all entities that a specific method calls (functions, other methods, classes)\n"
                "- Get all entities that a function calls\n"
                "- Get all entities that a class uses (e.g. instantiations, attribute access)\n"
                "- Build dependency graphs by entity ID for refactoring or impact analysis\n"
                "- Combine with get_entity_dependents for full call graph\n\n"
                "Important notes:\n"
                "- Use entity_name + entity_type when you have the name from code; the command resolves it to id.\n"
                "- Use entity_id when you already have the id (e.g. from list_code_entities).\n"
                "- If no dependencies are recorded (e.g. project not indexed or entity has no usages), returns empty list\n"
                "- Cross-ref is built from usages; run update_indexes after code changes to refresh"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db (or proxy socket)."
                    ),
                    "type": "string",
                    "required": True,
                },
                "entity_type": {
                    "description": (
                        "Type of the entity: 'class', 'method', or 'function'. Required when using entity_name."
                    ),
                    "type": "string",
                    "required": True,
                    "enum": list(CALLER_TYPES),
                },
                "entity_id": {
                    "description": (
                        "Database ID of the entity. Either entity_id or entity_name must be set."
                    ),
                    "type": "integer",
                    "required": False,
                    "examples": [1, 42, 100],
                },
                "entity_name": {
                    "description": (
                        "Name of the entity. Resolved to id within the project. Either entity_id or entity_name must be set. "
                        "For methods, optionally set target_class."
                    ),
                    "type": "string",
                    "required": False,
                },
                "target_class": {
                    "description": (
                        "Optional class name when entity_type is 'method' and entity_name is used."
                    ),
                    "type": "string",
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
                    "description": "Get dependencies of a function by id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                        "entity_id": 15,
                    },
                    "explanation": (
                        "Returns all entities (functions, methods, classes) that the function with id 15 "
                        "calls or uses. Use list_code_entities to get function ids."
                    ),
                },
                {
                    "description": "Get dependencies of a method by id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "method",
                        "entity_id": 42,
                    },
                    "explanation": (
                        "Returns all entities that the method with id 42 depends on (e.g. other methods, "
                        "functions, class instantiations)."
                    ),
                },
                {
                    "description": "Get dependencies of a class by id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "class",
                        "entity_id": 3,
                        "project_id": "a1b2c3d4-...",
                    },
                    "explanation": (
                        "Returns all entities that the class with id 3 uses (e.g. base classes, "
                        "functions called from class body). project_id optional if project is known."
                    ),
                },
                {
                    "description": "Get dependencies by name (no id needed)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                        "entity_name": "process_data",
                    },
                    "explanation": (
                        "Resolves 'process_data' to entity id in the project, then returns what that "
                        "function calls. Use when you have the name from code."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir points to directory but project not registered",
                    "solution": "Register project and run update_indexes first.",
                },
                "VALIDATION_ERROR": {
                    "description": "Invalid entity_type or neither entity_id nor entity_name provided",
                    "example": "entity_type not one of 'class', 'method', 'function', or both entity_id and entity_name omitted",
                    "solution": "Use exactly 'class', 'method', or 'function'; provide entity_id or entity_name.",
                },
                "ENTITY_NOT_FOUND": {
                    "description": "Entity name not found in project",
                    "example": "entity_name='foo' but no such class/function/method in project",
                    "solution": "Check spelling and that the project has been indexed (update_indexes).",
                },
                "GET_ENTITY_DEPENDENCIES_ERROR": {
                    "description": "General error during query",
                    "example": "Database error, proxy unavailable, or corrupted data",
                    "solution": "Check database integrity and proxy connection.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "dependencies": (
                            "List of dicts. Each has: callee_entity_type ('class'|'method'|'function'), "
                            "callee_entity_id, ref_type ('call'|'instantiation'|'attribute'|'inherit'), "
                            "file_path, line."
                        ),
                    },
                    "example": {
                        "dependencies": [
                            {
                                "callee_entity_type": "function",
                                "callee_entity_id": 8,
                                "ref_type": "call",
                                "file_path": "/path/to/project/src/main.py",
                                "line": 42,
                            },
                        ],
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


class GetEntityDependentsMCPCommand(BaseMCPCommand):
    """Get dependents of an entity (what calls/uses it) by entity id."""

    name = "get_entity_dependents"
    version = "1.0.0"
    descr = (
        "Get list of entities that depend on the given entity (by entity type and id)"
    )
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
                    "description": (
                        "Project root directory (contains data/code_analysis.db). "
                        "Can be absolute or relative."
                    ),
                },
                "entity_type": {
                    "type": "string",
                    "description": (
                        "Type of the entity: 'class', 'method', or 'function'. "
                        "Required when using entity_name."
                    ),
                    "enum": list(CALLEE_TYPES),
                },
                "entity_id": {
                    "type": "integer",
                    "description": (
                        "Database ID of the entity. Either entity_id or entity_name must be set. "
                        "Use entity_name when the caller knows only the name (e.g. from code)."
                    ),
                },
                "entity_name": {
                    "type": "string",
                    "description": (
                        "Name of the entity. Resolved to id within the project. "
                        "Either entity_id or entity_name must be set. Use with entity_type; "
                        "for methods, optionally set target_class to disambiguate."
                    ),
                },
                "target_class": {
                    "type": "string",
                    "description": (
                        "Optional class name when entity_type is 'method' and entity_name is used."
                    ),
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional project UUID; if omitted, inferred by root_dir."
                    ),
                },
            },
            "required": ["root_dir", "entity_type"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        entity_name: Optional[str] = None,
        target_class: Optional[str] = None,
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
            if entity_type not in CALLEE_TYPES:
                return ErrorResult(
                    message=f"entity_type must be one of {CALLEE_TYPES!r}",
                    code="VALIDATION_ERROR",
                )
            eid = entity_id
            if eid is None:
                if not entity_name:
                    return ErrorResult(
                        message="Provide entity_id or entity_name",
                        code="VALIDATION_ERROR",
                    )
                eid = _resolve_entity_id_by_name(
                    db, proj_id, entity_type, entity_name, target_class
                )
                if eid is None:
                    return ErrorResult(
                        message=f"Entity not found: {entity_type!r} {entity_name!r}",
                        code="ENTITY_NOT_FOUND",
                    )
            deps = _get_entity_dependents_via_execute(db, entity_type, eid)
            return SuccessResult(data={"dependents": deps})
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_DEPENDENTS_ERROR", "get_entity_dependents"
            )

    @classmethod
    def metadata(cls: type["GetEntityDependentsMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Provides comprehensive information including descriptions,
        usage examples, and edge cases. Detail level not less than one page.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The get_entity_dependents command returns the list of entities that depend on "
                "a given entity (what calls or uses it), using the entity cross-reference table. "
                "You can call it with entity_name + entity_type (resolved to id in the project) or with entity_id.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection via proxy\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. If entity_name given, resolves entity_name + entity_type to entity_id in the project; "
                "if entity_id given, uses it\n"
                "5. Queries entity_cross_ref table by callee_* column (class_id, method_id, or function_id)\n"
                "6. Resolves file_id to file_path for each row\n"
                "7. Returns list of caller entities with type, id, ref_type, file_path, line\n\n"
                "Data source:\n"
                "- The entity_cross_ref table is populated during update_file_data_atomic (and update_indexes) "
                "when usages are tracked. Each row links a caller entity to a callee entity. "
                "This command returns all callers of the given callee.\n\n"
                "Use cases:\n"
                "- Find all entities that call a specific function (impact analysis)\n"
                "- Find all entities that call a specific method\n"
                "- Find all entities that use a specific class (instantiation, inheritance)\n"
                "- Impact analysis before renaming or deleting an entity\n"
                "- Combine with get_entity_dependencies for full call graph\n\n"
                "Important notes:\n"
                "- Use entity_name + entity_type when you have the name from code; the command resolves it to id.\n"
                "- Use entity_id when you already have the id (e.g. from list_code_entities).\n"
                "- If no dependents are recorded, returns empty list\n"
                "- Cross-ref is built from usages; run update_indexes after code changes to refresh"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db (or proxy socket)."
                    ),
                    "type": "string",
                    "required": True,
                },
                "entity_type": {
                    "description": (
                        "Type of the entity: 'class', 'method', or 'function'. Required when using entity_name."
                    ),
                    "type": "string",
                    "required": True,
                    "enum": list(CALLEE_TYPES),
                },
                "entity_id": {
                    "description": (
                        "Database ID of the entity. Either entity_id or entity_name must be set."
                    ),
                    "type": "integer",
                    "required": False,
                    "examples": [1, 42, 100],
                },
                "entity_name": {
                    "description": (
                        "Name of the entity. Resolved to id within the project. "
                        "Either entity_id or entity_name must be set. For methods, optionally set target_class."
                    ),
                    "type": "string",
                    "required": False,
                },
                "target_class": {
                    "description": (
                        "Optional class name when entity_type is 'method' and entity_name is used."
                    ),
                    "type": "string",
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
                    "description": "Get dependents of a function by id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                        "entity_id": 8,
                    },
                    "explanation": (
                        "Returns all entities (functions, methods) that call the function with id 8. "
                        "Use for impact analysis before changing that function."
                    ),
                },
                {
                    "description": "Get dependents of a method by id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "method",
                        "entity_id": 42,
                    },
                    "explanation": (
                        "Returns all entities that call the method with id 42 (e.g. other methods, "
                        "functions)."
                    ),
                },
                {
                    "description": "Get dependents of a class by id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "class",
                        "entity_id": 3,
                        "project_id": "a1b2c3d4-...",
                    },
                    "explanation": (
                        "Returns all entities that use the class with id 3 (e.g. subclasses, "
                        "functions that instantiate it)."
                    ),
                },
                {
                    "description": "Get dependents by name (no id needed)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "entity_type": "function",
                        "entity_name": "process_data",
                    },
                    "explanation": (
                        "Resolves 'process_data' to entity id in the project, then returns who "
                        "calls it. Use when you have the name from code."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir points to directory but project not registered",
                    "solution": "Register project and run update_indexes first.",
                },
                "VALIDATION_ERROR": {
                    "description": "Invalid entity_type or neither entity_id nor entity_name provided",
                    "example": "entity_type not one of 'class', 'method', 'function', or both entity_id and entity_name omitted",
                    "solution": "Use exactly 'class', 'method', or 'function'; provide entity_id or entity_name.",
                },
                "ENTITY_NOT_FOUND": {
                    "description": "Entity name not found in project",
                    "example": "entity_name='foo' but no such class/function/method in project",
                    "solution": "Check spelling and that the project has been indexed (update_indexes).",
                },
                "GET_ENTITY_DEPENDENTS_ERROR": {
                    "description": "General error during query",
                    "example": "Database error, proxy unavailable, or corrupted data",
                    "solution": "Check database integrity and proxy connection.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "dependents": (
                            "List of dicts. Each has: caller_entity_type ('class'|'method'|'function'), "
                            "caller_entity_id, ref_type ('call'|'instantiation'|'attribute'|'inherit'), "
                            "file_path, line."
                        ),
                    },
                    "example": {
                        "dependents": [
                            {
                                "caller_entity_type": "function",
                                "caller_entity_id": 15,
                                "ref_type": "call",
                                "file_path": "/path/to/project/src/main.py",
                                "line": 42,
                            },
                        ],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "PROJECT_NOT_FOUND | VALIDATION_ERROR | ENTITY_NOT_FOUND | GET_ENTITY_DEPENDENTS_ERROR",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use entity_name + entity_type when you know the name from code (no need to resolve id first)",
                "Use get_entity_dependencies to find what an entity depends on (reverse direction)",
                "Run update_indexes after code changes so entity_cross_ref is up to date",
                "Use for impact analysis before refactoring or deleting an entity",
            ],
        }
