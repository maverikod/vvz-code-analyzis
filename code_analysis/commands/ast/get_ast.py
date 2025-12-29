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

            # Get AST from database
            ast_data = await db.get_ast_tree(file_record["id"])
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
