"""
MCP command wrapper: get_code_entity_info.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetCodeEntityInfoMCPCommand(BaseMCPCommand):
    """Get detailed information about a code entity (class, function, method)."""

    name = "get_code_entity_info"
    version = "1.0.0"
    descr = "Get detailed information about a class, function, or method"
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
                    "description": "Type of entity: 'class', 'function', or 'method'",
                    "enum": ["class", "function", "method"],
                },
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to search in (absolute or relative)",
                },
                "line": {
                    "type": "integer",
                    "description": "Optional line number for disambiguation",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "entity_type", "entity_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_type: str,
        entity_name: str,
        file_path: Optional[str] = None,
        line: Optional[int] = None,
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

            # Get entity info from database
            assert db.conn is not None
            cursor = db.conn.cursor()
            
            query = None
            params = []
            
            if entity_type == "class":
                query = "SELECT c.*, f.path as file_path FROM classes c JOIN files f ON c.file_id = f.id WHERE c.name = ? AND f.project_id = ?"
                params = [entity_name, proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                if line:
                    query += " AND c.line = ?"
                    params.append(line)
            elif entity_type == "function":
                query = "SELECT func.*, f.path as file_path FROM functions func JOIN files f ON func.file_id = f.id WHERE func.name = ? AND f.project_id = ?"
                params = [entity_name, proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND func.file_id = ?"
                        params.append(file_record["id"])
                if line:
                    query += " AND func.line = ?"
                    params.append(line)
            elif entity_type == "method":
                query = "SELECT m.*, c.name as class_name, f.path as file_path FROM methods m JOIN classes c ON m.class_id = c.id JOIN files f ON c.file_id = f.id WHERE m.name = ? AND f.project_id = ?"
                params = [entity_name, proj_id]
                if file_path:
                    file_record = db.get_file_by_path(file_path, proj_id)
                    if file_record:
                        query += " AND c.file_id = ?"
                        params.append(file_record["id"])
                if line:
                    query += " AND m.line = ?"
                    params.append(line)
            else:
                db.close()
                return ErrorResult(
                    message=f"Unknown entity type: {entity_type}",
                    code="INVALID_ENTITY_TYPE",
                )
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            db.close()

            if rows:
                entities = [dict(row) for row in rows]
                return SuccessResult(
                    data={
                        "success": True,
                        "entity_type": entity_type,
                        "entity_name": entity_name,
                        "entities": entities,
                        "count": len(entities),
                    }
                )
            return ErrorResult(
                message=f"Entity not found: {entity_type} {entity_name}",
                code="ENTITY_NOT_FOUND",
            )
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_INFO_ERROR", "get_code_entity_info"
            )
