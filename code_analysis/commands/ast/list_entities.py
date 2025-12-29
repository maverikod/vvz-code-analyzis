"""
MCP command wrapper: list_code_entities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ListCodeEntitiesMCPCommand(BaseMCPCommand):
    """List code entities (classes, functions, methods) in a file or project."""

    name = "list_code_entities"
    version = "1.0.0"
    descr = "List classes, functions, or methods in a file or project"
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
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', 'method', or null for all",
                    "enum": ["class", "function", "method"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
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
        entity_type: Optional[str] = None,
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

            # List entities from database
            entities = []
            
            if not entity_type or entity_type == "class":
                query = "SELECT c.*, f.path as file_path FROM classes c JOIN files f ON c.file_id = f.id WHERE f.project_id = ?"
                params = [proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                query += " ORDER BY f.path, c.line"
                if limit:
                    query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    entities.append({"type": "class", **row})
            
            if not entity_type or entity_type == "function":
                query = "SELECT func.*, f.path as file_path FROM functions func JOIN files f ON func.file_id = f.id WHERE f.project_id = ?"
                params = [proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND func.file_id = ?"
                        params.append(file_record["id"])
                query += " ORDER BY f.path, func.line"
                if limit:
                    query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    entities.append({"type": "function", **row})
            
            if not entity_type or entity_type == "method":
                query = "SELECT m.*, c.name as class_name, f.path as file_path FROM methods m JOIN classes c ON m.class_id = c.id JOIN files f ON c.file_id = f.id WHERE f.project_id = ?"
                params = [proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                query += " ORDER BY f.path, m.line"
                if limit:
                    query += f" LIMIT {limit}"
                if offset:
                    query += f" OFFSET {offset}"
                rows = db._fetchall(query, tuple(params))
                for row in rows:
                    entities.append({"type": "method", **row})
            
            db.close()
            
            return SuccessResult(
                data={
                    "success": True,
                    "entities": entities,
                    "count": len(entities),
                }
            )
        except Exception as e:
            return self._handle_error(e, "LIST_ENTITIES_ERROR", "list_code_entities")
