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
                    row = db._fetchone(
                        "SELECT * FROM files WHERE project_id = ? AND path LIKE ?",
                        (proj_id, f"%{file_path}")
                    )
                    if row:
                        file_record = row
                
                # Try by filename
                if not file_record and "/" in file_path:
                    filename = file_path.split("/")[-1]
                    rows = db._fetchall(
                        "SELECT * FROM files WHERE project_id = ? AND path LIKE ?",
                        (proj_id, f"%{filename}")
                    )
                    for row in rows:
                        path_str = row["path"]
                        if file_path in path_str or path_str.endswith(file_path):
                            file_record = row
                            break
                    if not file_record and rows:
                        file_record = rows[0]
                
                if not file_record:
                    db.close()
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
            
            rows = db._fetchall(query, tuple(params))
            
            imports = rows
            db.close()
            
            return SuccessResult(
                data={
                    "success": True,
                    "imports": imports,
                    "count": len(imports),
                }
            )
        except Exception as e:
            return self._handle_error(e, "GET_IMPORTS_ERROR", "get_imports")
