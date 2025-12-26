"""
MCP command wrapper: find_dependencies.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..find_dependencies import FindDependenciesCommand as InternalFindDependencies


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

            cmd = InternalFindDependencies(
                db,
                proj_id,
                entity_name=entity_name,
                entity_type=entity_type,
                target_class=target_class,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "find_dependencies failed"),
                code="FIND_DEPENDENCIES_ERROR",
                details=result,
            )
        except Exception as e:
            return self._handle_error(e, "FIND_DEPENDENCIES_ERROR", "find_dependencies")
