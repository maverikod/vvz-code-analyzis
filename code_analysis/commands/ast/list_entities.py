"""
MCP command wrapper: list_code_entities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ._common import get_project_id, logger, open_database
from ..list_code_entities import ListCodeEntitiesCommand as InternalListEntities


class ListCodeEntitiesMCPCommand(Command):
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
            db = open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            cmd = InternalListEntities(
                db,
                proj_id,
                entity_type=entity_type,
                file_path=file_path,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "list_code_entities failed"),
                code="LIST_ENTITIES_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("list_code_entities failed: %s", e)
            return ErrorResult(
                message=f"list_code_entities failed: {e}", code="LIST_ENTITIES_ERROR"
            )
