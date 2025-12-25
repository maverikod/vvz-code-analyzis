"""
MCP command wrapper: find_usages.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ._common import get_project_id, logger, open_database
from ..find_usages import FindUsagesCommand as InternalFindUsages


class FindUsagesMCPCommand(Command):
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
            db = open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            cmd = InternalFindUsages(
                db,
                proj_id,
                target_name=target_name,
                target_type=target_type,
                target_class=target_class,
                file_path=file_path,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "find_usages failed"),
                code="FIND_USAGES_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("find_usages failed: %s", e)
            return ErrorResult(
                message=f"find_usages failed: {e}", code="FIND_USAGES_ERROR"
            )
