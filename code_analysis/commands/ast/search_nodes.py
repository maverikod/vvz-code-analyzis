"""
MCP command wrapper: search_ast_nodes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class SearchASTNodesMCPCommand(BaseMCPCommand):
    """Search AST nodes across project/files."""

    name = "search_ast_nodes"
    version = "1.0.0"
    descr = "Search AST nodes (by type) in project files"
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
                "node_type": {
                    "type": "string",
                    "description": "AST node type to search (e.g., ClassDef, FunctionDef)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to limit search (absolute or relative)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 100,
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
        node_type: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 100,
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

            # Search AST nodes by type
            # We can search in classes, functions, methods tables
            # For more complex searches, would need to parse AST JSON
            results = []

            # Map node types to database tables
            if not node_type or node_type in ("ClassDef", "class"):
                # Search classes
                query = """
                    SELECT c.*, f.path as file_path
                    FROM classes c
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ?
                """
                params = [proj_id]

                if file_path:
                    from pathlib import Path

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

                    file_record = db.get_file_by_path(file_path, proj_id)
                    if not file_record:
                        row = db._fetchone(
                            "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                            (proj_id, f"%{file_path}"),
                        )
                        if row:
                            file_record = {"id": row["id"]}

                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])

                query += " ORDER BY f.path, c.line"
                if limit:
                    query += f" LIMIT {limit}"

                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    results.append(
                        {
                            "node_type": "ClassDef",
                            "name": row["name"],
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "docstring": row.get("docstring"),
                        }
                    )

            if not node_type or node_type in ("FunctionDef", "function"):
                # Search functions
                query = """
                    SELECT func.*, f.path as file_path
                    FROM functions func
                    JOIN files f ON func.file_id = f.id
                    WHERE f.project_id = ?
                """
                params = [proj_id]

                if file_path:
                    from pathlib import Path

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

                    file_record = db.get_file_by_path(file_path, proj_id)
                    if not file_record:
                        row = db._fetchone(
                            "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                            (proj_id, f"%{file_path}"),
                        )
                        if row:
                            file_record = {"id": row["id"]}

                    if file_record:
                        query += " AND func.file_id = ?"
                        params.append(file_record["id"])

                query += " ORDER BY f.path, func.line"
                if limit:
                    query += f" LIMIT {limit}"

                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    results.append(
                        {
                            "node_type": "FunctionDef",
                            "name": row["name"],
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "docstring": row.get("docstring"),
                        }
                    )

            if not node_type or node_type in ("method"):
                # Search methods
                query = """
                    SELECT m.*, c.name as class_name, f.path as file_path
                    FROM methods m
                    JOIN classes c ON m.class_id = c.id
                    JOIN files f ON c.file_id = f.id
                    WHERE f.project_id = ?
                """
                params = [proj_id]

                if file_path:
                    from pathlib import Path

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

                    file_record = db.get_file_by_path(file_path, proj_id)
                    if not file_record:
                        row = db._fetchone(
                            "SELECT id FROM files WHERE project_id = ? AND path LIKE ?",
                            (proj_id, f"%{file_path}"),
                        )
                        if row:
                            file_record = {"id": row["id"]}

                    if file_record:
                        query += " AND f.id = ?"
                        params.append(file_record["id"])

                query += " ORDER BY f.path, m.line"
                if limit:
                    query += f" LIMIT {limit}"

                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    results.append(
                        {
                            "node_type": "FunctionDef",
                            "name": row["name"],
                            "class_name": row.get("class_name"),
                            "file_path": row["file_path"],
                            "line": row["line"],
                            "docstring": row.get("docstring"),
                        }
                    )

            db.close()

            return SuccessResult(
                data={
                    "success": True,
                    "node_type": node_type,
                    "nodes": results,
                    "count": len(results),
                }
            )
        except Exception as e:
            return self._handle_error(e, "SEARCH_AST_ERROR", "search_ast_nodes")
