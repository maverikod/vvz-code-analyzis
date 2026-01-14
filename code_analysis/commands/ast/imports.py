"""
MCP command wrapper: get_imports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetImportsMCPCommand(BaseMCPCommand):
    """Get imports information from files or project."""

    name = "get_imports"
    version = "1.0.0"
    descr = "Get list of imports in a file or project with filtering options"
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
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
                },
                "import_type": {
                    "type": "string",
                    "description": "Type of import: 'import' or 'import_from'",
                    "enum": ["import", "import_from"],
                },
                "module_name": {
                    "type": "string",
                    "description": "Optional module name to filter by",
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
        file_path: Optional[str] = None,
        import_type: Optional[str] = None,
        module_name: Optional[str] = None,
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

            # Get imports from database
            query = "SELECT * FROM imports WHERE file_id IN (SELECT id FROM files WHERE project_id = ?)"
            params = [proj_id]

            if file_path:
                from pathlib import Path

                # Normalize file path
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

                # Try multiple path formats
                file_record = db.get_file_by_path(file_path, proj_id)

                # Try versioned path pattern
                if not file_record:
                    result = db.execute(
                        "SELECT * FROM files WHERE project_id = ? AND path LIKE ?",
                        (proj_id, f"%{file_path}"),
                    )
                    data = result.get("data", [])
                    if data:
                        file_record = data[0]

                # Try by filename
                if not file_record and "/" in file_path:
                    filename = file_path.split("/")[-1]
                    result = db.execute(
                        "SELECT * FROM files WHERE project_id = ? AND path LIKE ?",
                        (proj_id, f"%{filename}"),
                    )
                    rows = result.get("data", [])
                    for row in rows:
                        path_str = row["path"]
                        if file_path in path_str or path_str.endswith(file_path):
                            file_record = row
                            break
                    if not file_record and rows:
                        file_record = rows[0]

                if not file_record:
                    db.disconnect()
                    return ErrorResult(
                        message=f"File not found: {file_path}",
                        code="FILE_NOT_FOUND",
                    )
                query = "SELECT * FROM imports WHERE file_id = ?"
                params = [file_record["id"]]

            if import_type:
                query += " AND import_type = ?"
                params.append(import_type)

            if module_name:
                query += " AND module LIKE ?"
                params.append(f"%{module_name}%")

            query += " ORDER BY file_id, line"

            if limit:
                query += f" LIMIT {limit}"
            if offset:
                query += f" OFFSET {offset}"

            result = db.execute(query, tuple(params))
            rows = result.get("data", [])

            imports = rows
            db.disconnect()

            return SuccessResult(
                data={
                    "success": True,
                    "imports": imports,
                    "count": len(imports),
                }
            )
        except Exception as e:
            return self._handle_error(e, "GET_IMPORTS_ERROR", "get_imports")

    @classmethod
    def metadata(cls: type["GetImportsMCPCommand"]) -> Dict[str, Any]:
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
                "The get_imports command retrieves import information from files or the entire project. "
                "It returns a list of all import statements with filtering options by file, import type, "
                "and module name.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. If file_path provided:\n"
                "   - Normalizes file path (absolute to relative if possible)\n"
                "   - Tries multiple path matching strategies\n"
                "   - Filters imports to that specific file\n"
                "5. If file_path not provided, queries all imports in project\n"
                "6. Applies filters: import_type, module_name (LIKE pattern)\n"
                "7. Applies pagination: limit and offset\n"
                "8. Returns list of imports ordered by file_id and line\n\n"
                "Import Types:\n"
                "- 'import': Standard import statements (import os)\n"
                "- 'import_from': From-import statements (from os import path)\n\n"
                "Use cases:\n"
                "- List all imports in a file\n"
                "- Find all files importing a specific module\n"
                "- Analyze import dependencies\n"
                "- Check for unused imports\n"
                "- Understand module usage patterns\n\n"
                "Important notes:\n"
                "- Results ordered by file_id and line number\n"
                "- Supports pagination with limit and offset\n"
                "- module_name filter uses LIKE pattern matching\n"
                "- Path resolution is flexible to handle versioned files"
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
                "file_path": {
                    "description": (
                        "Optional file path to filter by. If provided, only returns imports "
                        "from this specific file. Can be absolute or relative to root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
                "import_type": {
                    "description": (
                        "Type of import to filter by. Optional. Options: 'import' or 'import_from'. "
                        "If null, returns all import types."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": ["import", "import_from"],
                },
                "module_name": {
                    "description": (
                        "Optional module name to filter by. Uses LIKE pattern matching, so partial "
                        "matches are supported. Example: 'os' matches 'os', 'os.path', etc."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["os", "json", "code_analysis"],
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
                    "description": "Get all imports in a file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Returns all import statements from src/main.py file."
                    ),
                },
                {
                    "description": "Get all imports in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns all import statements across the entire project."
                    ),
                },
                {
                    "description": "Find all files importing a module",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "module_name": "os",
                    },
                    "explanation": (
                        "Finds all files that import 'os' module (or modules containing 'os')."
                    ),
                },
                {
                    "description": "Get only import_from statements",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "import_type": "import_from",
                    },
                    "explanation": (
                        "Returns only 'from X import Y' style imports, excluding 'import X' statements."
                    ),
                },
                {
                    "description": "Get imports with pagination",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "limit": 100,
                        "offset": 0,
                    },
                    "explanation": (
                        "Returns first 100 imports. Use offset for next page."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "FILE_NOT_FOUND": {
                    "description": "File not found in database",
                    "example": "file_path='src/main.py' but file not in database",
                    "solution": (
                        "Ensure file exists and has been indexed. Check file path is correct. "
                        "Run update_indexes to index files."
                    ),
                },
                "GET_IMPORTS_ERROR": {
                    "description": "General error during import retrieval",
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
                        "imports": (
                            "List of import dictionaries from database. Each contains:\n"
                            "- file_id: Database ID of file\n"
                            "- line: Line number where import occurs\n"
                            "- import_type: Type of import ('import' or 'import_from')\n"
                            "- module: Module name (for import_from) or null\n"
                            "- name: Imported name\n"
                            "- Additional database fields as available"
                        ),
                        "count": "Number of imports found",
                    },
                    "example": {
                        "success": True,
                        "imports": [
                            {
                                "file_id": 1,
                                "line": 1,
                                "import_type": "import",
                                "module": None,
                                "name": "os",
                            },
                            {
                                "file_id": 1,
                                "line": 2,
                                "import_type": "import_from",
                                "module": "json",
                                "name": "loads",
                            },
                        ],
                        "count": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FILE_NOT_FOUND, GET_IMPORTS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use file_path filter to focus on specific file imports",
                "Use module_name filter to find module usage patterns",
                "Use import_type filter to separate import styles",
                "Use limit and offset for pagination with large result sets",
                "Combine with export_graph (graph_type='dependencies') for visualization",
            ],
        }
