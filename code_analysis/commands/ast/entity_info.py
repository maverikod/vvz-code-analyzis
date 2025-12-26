"""
MCP command wrapper: get_code_entity_info.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..get_code_entity_info import GetCodeEntityInfoCommand as InternalGetEntityInfo


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

            cmd = InternalGetEntityInfo(
                db, proj_id, entity_type, entity_name, file_path=file_path, line=line
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "get_code_entity_info failed"),
                code="GET_ENTITY_INFO_ERROR",
                details=result,
            )
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_INFO_ERROR", "get_code_entity_info"
            )
