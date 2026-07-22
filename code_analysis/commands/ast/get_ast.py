"""
MCP command wrapper: get_ast.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .file_resolution import resolve_project_file_record
from ..base_mcp_command import BaseMCPCommand
from ...core.database_driver_pkg.domain.ast_cst import get_ast as get_ast_via_driver
from ...core.exceptions import ValidationError


class GetASTMCPCommand(BaseMCPCommand):
    """Retrieve stored AST for a given file."""

    name = "get_ast"
    version = "1.0.0"
    descr = "Get AST for a Python file from the analysis database"
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @staticmethod
    def _resolve_file_system_path(
        file_record: Dict[str, Any], project_root: Path, normalized_file_path: str
    ) -> Path:
        """Resolve filesystem path from DB record with safe fallbacks."""
        db_path = file_record.get("path")
        if isinstance(db_path, str) and db_path:
            p = Path(db_path)
            if p.is_absolute():
                return p
            return (project_root / p).resolve()
        return (project_root / normalized_file_path).resolve()

    @staticmethod
    def _has_searchable_ast_index(db: Any, project_id: str, file_id: Any) -> bool:
        """
        True when file is searchable via AST-related entity indexes.

        search_ast_nodes uses classes/functions/methods tables, so get_ast must not
        return AST_NOT_INDEXED if at least one of these has rows for the same file.
        """
        result = db.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM classes c
               JOIN files f ON c.file_id = f.id
               WHERE c.file_id = ? AND f.project_id = ?) AS classes_count,
              (SELECT COUNT(*) FROM functions fn
               JOIN files f ON fn.file_id = f.id
               WHERE fn.file_id = ? AND f.project_id = ?) AS functions_count,
              (SELECT COUNT(*) FROM methods m
               JOIN classes c ON m.class_id = c.id
               JOIN files f ON c.file_id = f.id
               WHERE c.file_id = ? AND f.project_id = ?) AS methods_count
            """,
            (file_id, project_id, file_id, project_id, file_id, project_id),
        )
        rows = GetASTMCPCommand._normalize_execute_rows(result)
        if not rows:
            return False
        return GetASTMCPCommand._row_has_searchable_counts(rows[0])

    @staticmethod
    def _normalize_execute_rows(result: Any) -> list[dict[str, Any]]:
        """Normalize db.execute result into list[dict] across backends."""
        if result is None:
            return []

        raw_rows: Any = []
        if isinstance(result, dict):
            raw_rows = result.get("data", [])
        elif isinstance(result, (list, tuple)):
            raw_rows = result
        else:
            data_attr = getattr(result, "data", None)
            if data_attr is not None:
                raw_rows = data_attr
            else:
                # Single row-like object returned directly.
                raw_rows = [result]

        if raw_rows is None:
            return []
        if isinstance(raw_rows, dict):
            raw_rows = [raw_rows]
        elif not isinstance(raw_rows, (list, tuple)):
            raw_rows = [raw_rows]

        normalized: list[dict[str, Any]] = []
        for row in raw_rows:
            mapped = GetASTMCPCommand._normalize_row_mapping(row)
            if mapped:
                normalized.append(mapped)
        return normalized

    @staticmethod
    def _normalize_row_mapping(row: Any) -> dict[str, Any]:
        """Convert one row-like object to plain dict when possible."""
        if row is None:
            return {}
        if isinstance(row, dict):
            return row
        if hasattr(row, "keys"):
            try:
                return {key: row[key] for key in row.keys()}
            except Exception:
                pass
        if hasattr(row, "_mapping"):
            try:
                return dict(row._mapping)
            except Exception:
                pass
        # DB adapters may return positional rows: (classes_count, functions_count, methods_count)
        if isinstance(row, (list, tuple)) and len(row) >= 3:
            return {
                "classes_count": row[0],
                "functions_count": row[1],
                "methods_count": row[2],
            }
        # Some adapters may return a single scalar count.
        if isinstance(row, (int, float, bool)):
            return {"classes_count": row, "functions_count": 0, "methods_count": 0}
        return {}

    @staticmethod
    def _row_has_searchable_counts(row: dict[str, Any]) -> bool:
        """Return True when any known AST-entity count is positive."""

        def _as_int(value: Any) -> int:
            """Return as int."""
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        total = _as_int(row.get("classes_count"))
        total += _as_int(row.get("functions_count"))
        total += _as_int(row.get("methods_count"))
        return total > 0

    @staticmethod
    def _parse_ast_from_disk(file_path: Path) -> str:
        """Parse Python file into JSON-serializable AST payload."""
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        return ast.dump(tree, annotate_fields=True, include_attributes=True)

    @staticmethod
    def _ast_not_indexed_message(normalized_file_path: str) -> str:
        """User-facing message when AST data is not yet available."""
        return (
            f"AST not indexed for file: {normalized_file_path}. "
            "File may still be indexing; please wait and retry."
        )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (relative to project root)",
                },
                "include_json": {
                    "type": "boolean",
                    "description": "Include full AST JSON in response",
                    "default": True,
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        include_json: bool = True,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute the command."""
        params: Dict[str, Any] = {
            "project_id": project_id,
            "file_path": file_path,
            "include_json": include_json,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "get_ast")
        project_id = params["project_id"]
        file_path = params["file_path"]
        include_json = bool(params.get("include_json", True))

        try:
            root_path = self._resolve_project_root(project_id)
            db = self._open_database_from_config(auto_analyze=False)
            resolution = resolve_project_file_record(
                db=db,
                project_id=project_id,
                project_root=root_path,
                file_path=file_path,
            )
            file_record = resolution["file_record"]
            normalized_file_path = resolution["normalized_file_path"]

            if not file_record:
                db.disconnect()
                if resolution["exists_on_disk"]:
                    return ErrorResult(
                        message=self._ast_not_indexed_message(normalized_file_path),
                        code="AST_NOT_INDEXED",
                    )
                return ErrorResult(
                    message=f"File not found: {normalized_file_path}",
                    code="FILE_NOT_FOUND",
                )

            # Get AST from database. DatabaseClient.get_ast() returns parsed AST dict;
            # direct DB get_ast_tree() returns row with "ast_json" string.
            file_id = (
                file_record["id"] if isinstance(file_record, dict) else file_record.id
            )
            ast_data = get_ast_via_driver(db, file_id)

            if ast_data is not None:
                result = {
                    "success": True,
                    "file_path": normalized_file_path,
                    "file_id": file_id,
                }
                if include_json:
                    if isinstance(ast_data, dict) and "ast_json" in ast_data:
                        import json

                        result["ast"] = json.loads(ast_data["ast_json"])
                    else:
                        result["ast"] = ast_data
                db.disconnect()
                return SuccessResult(data=result)

            # Align get_ast behavior with search_ast_nodes/file_structure sources.
            # If file is already searchable via entity indexes, treat it as indexed.
            searchable_index_exists = self._has_searchable_ast_index(
                db, project_id=project_id, file_id=file_id
            )
            if searchable_index_exists:
                result = {
                    "success": True,
                    "file_path": normalized_file_path,
                    "file_id": file_id,
                }
                if include_json:
                    fs_path = self._resolve_file_system_path(
                        file_record=file_record,
                        project_root=root_path,
                        normalized_file_path=normalized_file_path,
                    )
                    if fs_path.exists() and fs_path.is_file():
                        result["ast"] = self._parse_ast_from_disk(fs_path)
                db.disconnect()
                return SuccessResult(data=result)

            db.disconnect()
            return ErrorResult(
                message=self._ast_not_indexed_message(normalized_file_path),
                code="AST_NOT_INDEXED",
            )
        except Exception as e:
            return self._handle_error(e, "GET_AST_ERROR", "get_ast")

    @classmethod
    def metadata(cls: type["GetASTMCPCommand"]) -> Dict[str, Any]:
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
                "The get_ast command retrieves the stored Abstract Syntax Tree (AST) for a Python file "
                "from the analysis database. The AST is stored as JSON and represents the complete "
                "syntactic structure of the Python code.\n\n"
                "Operation flow:\n"
                "1. Validates project_id via project registry\n"
                "2. Opens database connection for the project\n"
                "3. Normalizes file_path (converts absolute to relative if possible)\n"
                "4. Attempts multiple path matching strategies:\n"
                "   - Exact path match\n"
                "   - Versioned path pattern (data/versions/{uuid}/...)\n"
                "   - Filename match (if path contains /)\n"
                "5. Retrieves AST tree from database for the file\n"
                "6. If include_json=true, parses and includes full AST JSON\n"
                "7. Returns file metadata and optionally AST JSON\n\n"
                "Path Resolution:\n"
                "The command tries multiple strategies to find the file:\n"
                "1. Exact path match against database\n"
                "2. Versioned path pattern matching (for files in versioned storage)\n"
                "3. Filename matching (if multiple matches, prefers path structure match)\n\n"
                "Use cases:\n"
                "- Retrieve AST for code analysis\n"
                "- Inspect code structure programmatically\n"
                "- Build tools that work with AST\n"
                "- Verify AST data exists for a file\n"
                "- Extract code structure information\n\n"
                "Important notes:\n"
                "- AST must be stored in database (created during file analysis)\n"
                "- AST JSON can be large for big files\n"
                "- Set include_json=false to get metadata only\n"
                "- Path resolution is flexible to handle versioned files"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID (from create_project or list_projects)."
                    ),
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": (
                        "Path to Python file. Can be absolute or relative to project root. "
                        "Command tries multiple matching strategies to find the file in database."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "src/main.py",
                        "/home/user/projects/my_project/src/main.py",
                        "code_analysis/core/parser.py",
                    ],
                },
                "include_json": {
                    "description": (
                        "If true, includes full AST JSON in response. If false, returns only "
                        "metadata (file_path, file_id as UUID string for files.id). Default is true. "
                        "Set to false for large files to reduce response size."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            },
            "usage_examples": [
                {
                    "description": "Get AST with JSON for a file",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "src/main.py",
                        "include_json": True,
                    },
                    "explanation": (
                        "Retrieves full AST JSON for src/main.py. Use for detailed AST analysis."
                    ),
                },
                {
                    "description": "Check if AST exists without retrieving JSON",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "src/main.py",
                        "include_json": False,
                    },
                    "explanation": (
                        "Checks if AST exists for file without retrieving large JSON. "
                        "Useful for verification before detailed analysis."
                    ),
                },
                {
                    "description": "Get AST using absolute path",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "/home/user/projects/my_project/src/main.py",
                    },
                    "explanation": (
                        "Uses absolute path. Command will normalize to relative path if possible."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "project_id='invalid-uuid' not registered",
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
                "AST_NOT_FOUND": {
                    "description": "AST not found for file",
                    "example": "File exists in database but has no AST tree",
                    "solution": (
                        "File may not have been analyzed yet. Run update_indexes or analyze_file "
                        "to create AST for the file."
                    ),
                },
                "GET_AST_ERROR": {
                    "description": "General error during AST retrieval",
                    "example": "Database error, JSON parsing error, or corrupted data",
                    "solution": (
                        "Check database connectivity, verify file_path parameter, ensure AST data "
                        "is valid. Try restore_database if database is corrupted."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "file_path": "File path (normalized)",
                        "file_id": "files.id primary key (UUID string after DB UUID migration)",
                        "ast": (
                            "Full AST JSON (if include_json=true). "
                            "AST structure follows Python AST module format with node types, "
                            "line numbers, and code structure."
                        ),
                    },
                    "example_with_json": {
                        "success": True,
                        "file_path": "src/main.py",
                        "file_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                        "ast": {
                            "_type": "Module",
                            "body": [
                                {
                                    "_type": "FunctionDef",
                                    "name": "main",
                                    "lineno": 1,
                                    "col_offset": 0,
                                }
                            ],
                        },
                    },
                    "example_without_json": {
                        "success": True,
                        "file_path": "src/main.py",
                        "file_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FILE_NOT_FOUND, AST_NOT_FOUND, GET_AST_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Set include_json=false for large files to reduce response size",
                "Use this command to verify AST exists before AST-dependent operations",
                "AST JSON follows Python AST module structure for compatibility",
                "Path resolution is flexible - use relative paths when possible",
                "Combine with other AST commands for comprehensive code analysis",
            ],
        }
