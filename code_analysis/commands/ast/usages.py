"""
MCP command wrapper: find_usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.exceptions import ValidationError
from ...core.cst_tree.models import CSTTree
from ...core.cst_tree.tree_builder import load_file_to_tree
from ...core.cst_tree.tree_range_finder import find_node_by_range
from ...core.file_identity import relative_path_for_indexed_row
from ...core.uuid_validation import is_valid_uuid4 as _is_valid_uuid4


def _load_tree_for_read(abs_path: Path) -> Optional[CSTTree]:
    """
    Load ``abs_path`` into a CST tree for a READ-ONLY lookup (no disk writes).

    Returns None when the file is missing, not a ``.py`` file, or fails to parse -
    callers treat that as "no cst_node_id available" for every usage in that file.
    """
    if not abs_path.exists() or abs_path.suffix != ".py":
        return None
    try:
        return load_file_to_tree(str(abs_path), write_to_disk=False)
    except (FileNotFoundError, ValueError, OSError):
        return None


def _resolve_usages_with_cst_node_id(
    root_path: Path, raw_usages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Resolve cst_node_id for each usage by file_path and line. Return only
    usages that have valid UUID4 cst_node_id (no response path without it).

    Builds the CST tree ONCE per distinct file (cached in ``tree_by_path`` for
    the lifetime of this call) and resolves every usage line of that file
    against the cached tree, instead of re-parsing per usage record. The read
    never writes to disk (``load_file_to_tree(..., write_to_disk=False)``).
    """
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for u in raw_usages:
        fp = u.get("file_path") or ""
        if fp not in by_file:
            by_file[fp] = []
        by_file[fp].append(u)

    tree_by_path: Dict[Path, Optional[CSTTree]] = {}
    resolved: List[Dict[str, Any]] = []
    for fpath, group in by_file.items():
        abs_path = (root_path / fpath).resolve()
        if abs_path not in tree_by_path:
            tree_by_path[abs_path] = _load_tree_for_read(abs_path)
        tree = tree_by_path[abs_path]
        if tree is None:
            continue
        for rec in group:
            line = rec.get("line")
            if line is None:
                continue
            node = find_node_by_range(tree.tree_id, line, line, prefer_exact=False)
            node_id = node.node_id if node else None
            if not _is_valid_uuid4(node_id):
                continue
            out = dict(rec)
            out["cst_node_id"] = node_id
            resolved.append(out)
    return resolved


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
        """Return the command input schema."""
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
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
            },
            "required": ["project_id", "target_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        target_name: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute the command."""
        call_params: Dict[str, Any] = {
            "project_id": project_id,
            "target_name": target_name,
            "target_type": target_type,
            "target_class": target_class,
            "file_path": file_path,
            "limit": limit,
            "offset": offset,
        }
        call_params.update(kwargs)
        try:
            call_params = self.validate_params(call_params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "find_usages")
        project_id = call_params["project_id"]
        target_name = call_params["target_name"]
        target_type = call_params.get("target_type")
        target_class = call_params.get("target_class")
        file_path = call_params.get("file_path")
        limit = call_params.get("limit")
        offset = int(call_params.get("offset", 0))

        try:
            root_path = self._resolve_project_root(project_id)
            db = self._open_database()
            proj_id = project_id

            # Find usages from database
            # Uses multiple sources for comprehensive results:
            # - usages table: actual function calls, method calls, class instantiations
            # - imports table: module/class/function imports
            # - classes table: inheritance relationships (bases)
            raw_usages: List[Dict[str, Any]] = []

            # Search in imports table for class/function usages
            if target_type in ("class", "function", None):
                import_query = """
                    SELECT i.*, f.path as file_path, f.relative_path as file_relative_path,
                           f.id as file_id
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
                    raw_usages.append(
                        {
                            "file_id": row["file_id"],
                            "file_path": relative_path_for_indexed_row(
                                {
                                    "path": row.get("file_path"),
                                    "relative_path": row.get("file_relative_path"),
                                },
                                root_path,
                            ),
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
                    SELECT c.*, f.path as file_path, f.relative_path as file_relative_path,
                           f.id as file_id
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
                        raw_usages.append(
                            {
                                "file_id": row["file_id"],
                                "file_path": relative_path_for_indexed_row(
                                    {
                                        "path": row.get("file_path"),
                                        "relative_path": row.get("file_relative_path"),
                                    },
                                    root_path,
                                ),
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
                SELECT u.*, f.path as file_path, f.relative_path as file_relative_path,
                       f.id as file_id
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
                raw_usages.append(
                    {
                        "file_id": row["file_id"],
                        "file_path": relative_path_for_indexed_row(
                            {
                                "path": row.get("file_path"),
                                "relative_path": row.get("file_relative_path"),
                            },
                            root_path,
                        ),
                        "line": row["line"],
                        "target_name": row["target_name"],
                        "target_type": row["target_type"],
                        "target_class": row.get("target_class"),
                        "usage_type": row.get("usage_type", "usage"),
                        "context": row.get("context"),
                    }
                )

            db.disconnect()

            # Resolve cst_node_id for each usage; keep only records with valid UUID4
            usages = _resolve_usages_with_cst_node_id(root_path, raw_usages)

            # Apply limit and offset to final results
            if limit:
                usages = usages[offset : offset + limit]
            elif offset:
                usages = usages[offset:]

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
            "parameters_summary": (
                "Required: project_id, target_name. Optional: target_type (method|property|class|function), "
                "target_class, file_path, limit, offset. Use target_name and target_type, not entity_name/entity_type."
            ),
            "detailed_description": (
                "The find_usages command finds all places where a method, property, class, or function "
                "is used in the project. It searches the usages table in the analysis database to "
                "locate all references to the target entity.\n\n"
                "Operation flow:\n"
                "1. Validates project_id via project registry\n"
                "2. Opens database connection for the project\n"
                "3. Builds query filtering by target_name, target_type, target_class, file_path\n"
                "4. If file_path provided, limits search to that specific file\n"
                "5. Applies pagination: limit and offset\n"
                "6. Returns list of usages with file_path and valid UUID4 cst_node_id per entity\n\n"
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
                "- Each usage entity includes file_path and valid UUID4 cst_node_id; no response without cst_node_id\n"
                "- Supports pagination with limit and offset\n"
                "- For methods, use target_class to disambiguate\n"
                "- If file_path provided, searches only in that file"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID (from create_project or list_projects)."
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
                        "within this specific file. Can be absolute or relative to project root."
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
            },
            "usage_examples": [
                {
                    "description": "Find all usages of a function",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                    "example": "project_id='invalid-uuid' not registered",
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
                            "List of usage records. Each contains file_path and valid UUID4 cst_node_id.\n"
                            "- file_path: Path to file where usage occurs (relative to project root)\n"
                            "- cst_node_id: UUID4 CST node identifier (required; no record without it)\n"
                            "- line: Line number where usage occurs\n"
                            "- target_name, target_type, target_class, usage_type, etc.\n"
                            "- No fallback identity by line/range; only entities with resolved cst_node_id"
                        ),
                        "count": "Number of usages found",
                    },
                    "example": {
                        "success": True,
                        "target_name": "process_data",
                        "usages": [
                            {
                                "file_path": "src/main.py",
                                "cst_node_id": "550e8400-e29b-41d4-a716-446655440000",
                                "line": 42,
                                "target_name": "process_data",
                                "target_type": "function",
                                "target_class": None,
                            },
                            {
                                "file_path": "tests/test_main.py",
                                "cst_node_id": "660e8400-e29b-41d4-a716-446655440001",
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
