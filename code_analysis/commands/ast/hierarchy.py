"""
MCP command wrapper: get_class_hierarchy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ._common import get_project_id, logger, open_database
from ..get_class_hierarchy import GetClassHierarchyCommand as InternalGetClassHierarchy


class GetClassHierarchyMCPCommand(Command):
    """Get class hierarchy (inheritance tree)."""

    name = "get_class_hierarchy"
    version = "1.0.0"
    descr = "Get class inheritance hierarchy for a specific class or all classes"
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
                "class_name": {
                    "type": "string",
                    "description": "Optional class name to get hierarchy for (if null, returns all hierarchies)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
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
        class_name: Optional[str] = None,
        file_path: Optional[str] = None,
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

            cmd = InternalGetClassHierarchy(
                db, proj_id, class_name=class_name, file_path=file_path
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "get_class_hierarchy failed"),
                code="GET_CLASS_HIERARCHY_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("get_class_hierarchy failed: %s", e)
            return ErrorResult(
                message=f"get_class_hierarchy failed: {e}",
                code="GET_CLASS_HIERARCHY_ERROR",
            )
