"""
MCP command wrapper: get_ast.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetASTMCPCommand(BaseMCPCommand):
    """Retrieve stored AST for a given file."""

    name = "get_ast"
    version = "1.0.0"
    descr = "Get AST for a Python file from the analysis database"
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
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "include_json": {
                    "type": "boolean",
                    "description": "Include full AST JSON in response",
                    "default": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        include_json: bool = True,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            from pathlib import Path
            
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Normalize file path: convert absolute to relative if needed
            file_path_obj = Path(file_path)
            if file_path_obj.is_absolute():
                try:
                    # Try to make relative to root_dir
                    normalized_path = file_path_obj.relative_to(root_path)
                    file_path = str(normalized_path)
                except ValueError:
                    # File is outside root_dir, use absolute path as-is
                    pass
            else:
                # Already relative, use as-is
                file_path = str(file_path_obj)

            # Get file_id first - try multiple path formats
            file_record = None
            
            # Try 1: exact path match
            file_record = db.get_file_by_path(file_path, proj_id)
            
            # Try 2: if not found, try with versioned path pattern
            if not file_record:
                # Files in DB may be stored with versioned paths like:
                # data/versions/{uuid}/code_analysis/main.py
                # Try searching by path ending
                # Search for files where path ends with the requested path
                row = db._fetchone(
                    "SELECT * FROM files WHERE project_id = ? AND path LIKE ?",
                    (proj_id, f"%{file_path}")
                )
                if row:
                    file_record = row
            
            # Try 3: search by filename if path contains /
            if not file_record and "/" in file_path:
                filename = file_path.split("/")[-1]
                rows = db._fetchall(
                    "SELECT * FROM files WHERE project_id = ? AND path LIKE ?",
                    (proj_id, f"%{filename}")
                )
                # If multiple matches, prefer the one that matches the path structure
                for row in rows:
                    path_str = row["path"]
                    if file_path in path_str or path_str.endswith(file_path):
                        file_record = row
                        break
                # If still no match, use first result
                if not file_record and rows:
                    file_record = rows[0]
            
            if not file_record:
                db.close()
                return ErrorResult(
                    message=f"File not found: {file_path}",
                    code="FILE_NOT_FOUND",
                )

            # Get AST from database (synchronous method, no await needed)
            ast_data = db.get_ast_tree(file_record["id"])
            db.close()

            if ast_data:
                result = {
                    "success": True,
                    "file_path": file_path,
                    "file_id": file_record["id"],
                }
                if include_json and ast_data.get("ast_json"):
                    import json
                    result["ast"] = json.loads(ast_data["ast_json"])
                return SuccessResult(data=result)
            return ErrorResult(
                message="AST not found for file",
                code="AST_NOT_FOUND",
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
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Normalizes file_path (converts absolute to relative if possible)\n"
                "5. Attempts multiple path matching strategies:\n"
                "   - Exact path match\n"
                "   - Versioned path pattern (data/versions/{uuid}/...)\n"
                "   - Filename match (if path contains /)\n"
                "6. Retrieves AST tree from database for the file\n"
                "7. If include_json=true, parses and includes full AST JSON\n"
                "8. Returns file metadata and optionally AST JSON\n\n"
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
                        "metadata (file_path, file_id). Default is true. Set to false for "
                        "large files to reduce response size."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
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
                    "description": "Get AST with JSON for a file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
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
                        "root_dir": "/home/user/projects/my_project",
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
                        "root_dir": "/home/user/projects/my_project",
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
                        "Check database integrity, verify file_path parameter, ensure AST data "
                        "is valid. Try repair_sqlite_database if database is corrupted."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "file_path": "File path (normalized)",
                        "file_id": "Database ID of file",
                        "ast": (
                            "Full AST JSON (if include_json=true). "
                            "AST structure follows Python AST module format with node types, "
                            "line numbers, and code structure."
                        ),
                    },
                    "example_with_json": {
                        "success": True,
                        "file_path": "src/main.py",
                        "file_id": 1,
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
                        "file_id": 1,
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
