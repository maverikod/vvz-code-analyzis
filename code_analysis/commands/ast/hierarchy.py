"""
MCP command wrapper: get_class_hierarchy.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class GetClassHierarchyMCPCommand(BaseMCPCommand):
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
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Get class hierarchy from database
            # This requires parsing AST or checking base classes in classes table
            # For now, return placeholder
            db.close()
            return ErrorResult(
                message="Class hierarchy requires AST parsing or base_classes column in classes table",
                code="NOT_IMPLEMENTED",
            )
        except Exception as e:
            return self._handle_error(
                e, "GET_CLASS_HIERARCHY_ERROR", "get_class_hierarchy"
            )
