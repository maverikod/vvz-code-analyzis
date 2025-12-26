"""
MCP command wrapper: find_usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


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
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
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
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "target_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        target_name: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
        file_path: Optional[str] = None,
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

            # Find usages from database
            assert db.conn is not None
            cursor = db.conn.cursor()
            
            query = "SELECT * FROM usages WHERE file_id IN (SELECT id FROM files WHERE project_id = ?)"
            params = [proj_id]
            
            if target_name:
                query += " AND target_name = ?"
                params.append(target_name)
            
            if target_type:
                query += " AND target_type = ?"
                params.append(target_type)
            
            if target_class:
                query += " AND target_class = ?"
                params.append(target_class)
            
            if file_path:
                file_record = db.get_file_by_path(file_path, proj_id)
                if file_record:
                    query = "SELECT * FROM usages WHERE file_id = ?"
                    params = [file_record["id"]]
                    if target_name:
                        query += " AND target_name = ?"
                        params.append(target_name)
            
            query += " ORDER BY file_id, line"
            
            if limit:
                query += f" LIMIT {limit}"
            if offset:
                query += f" OFFSET {offset}"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            usages = [dict(row) for row in rows]
            db.close()
            
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
