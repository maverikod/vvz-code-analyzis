"""
MCP command wrapper: find_dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class FindDependenciesMCPCommand(BaseMCPCommand):
    """Find dependencies - where classes, functions, or modules are used."""

    name = "find_dependencies"
    version = "1.0.0"
    descr = "Find where a class, function, method, or module is used in the project"
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
                "entity_name": {
                    "type": "string",
                    "description": "Name of entity to find dependencies for",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', 'method', 'module', or null for all",
                    "enum": ["class", "function", "method", "module"],
                },
                "target_class": {
                    "type": "string",
                    "description": "Optional class name for methods",
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
            "required": ["root_dir", "entity_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_name: str,
        entity_type: Optional[str] = None,
        target_class: Optional[str] = None,
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

            # Find dependencies from database
            # Dependencies table stores file-to-file dependencies
            # For entity dependencies, we search through usages and imports
            assert db.conn is not None
            cursor = db.conn.cursor()
            
            results = []
            
            # Search in usages table for entity usages
            if entity_type in ("class", "function", "method", None):
                usage_query = """
                    SELECT u.*, f.path as file_path
                    FROM usages u
                    JOIN files f ON u.file_id = f.id
                    WHERE f.project_id = ? AND u.target_name = ?
                """
                usage_params = [proj_id, entity_name]
                
                if entity_type:
                    usage_query += " AND u.target_type = ?"
                    usage_params.append(entity_type)
                
                if target_class:
                    usage_query += " AND u.target_class = ?"
                    usage_params.append(target_class)
                
                usage_query += " ORDER BY f.path, u.line"
                if limit:
                    usage_query += f" LIMIT {limit}"
                if offset:
                    usage_query += f" OFFSET {offset}"
                
                cursor.execute(usage_query, usage_params)
                usage_rows = cursor.fetchall()
                for row in usage_rows:
                    results.append({
                        "type": "usage",
                        "file_path": row["file_path"],
                        "line": row["line"],
                        "target_name": row["target_name"],
                        "target_type": row["target_type"],
                        "target_class": row.get("target_class"),
                    })
            
            # Search in imports table for module dependencies
            if entity_type in ("module", None):
                import_query = """
                    SELECT i.*, f.path as file_path
                    FROM imports i
                    JOIN files f ON i.file_id = f.id
                    WHERE f.project_id = ? AND (i.name = ? OR i.module LIKE ?)
                """
                import_params = [proj_id, entity_name, f"%{entity_name}%"]
                
                import_query += " ORDER BY f.path, i.line"
                if limit:
                    import_query += f" LIMIT {limit}"
                if offset:
                    import_query += f" OFFSET {offset}"
                
                cursor.execute(import_query, import_params)
                import_rows = cursor.fetchall()
                for row in import_rows:
                    results.append({
                        "type": "import",
                        "file_path": row["file_path"],
                        "line": row["line"],
                        "module": row.get("module"),
                        "name": row["name"],
                        "import_type": row["import_type"],
                    })
            
            db.close()
            
            return SuccessResult(
                data={
                    "success": True,
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "dependencies": results,
                    "count": len(results),
                }
            )
        except Exception as e:
            return self._handle_error(e, "FIND_DEPENDENCIES_ERROR", "find_dependencies")
