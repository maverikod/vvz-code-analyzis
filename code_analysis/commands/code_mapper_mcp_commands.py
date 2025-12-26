"""
MCP commands for code_mapper functionality (long files, errors by category).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from .code_mapper_commands import ListLongFilesCommand, ListErrorsByCategoryCommand

logger = logging.getLogger(__name__)


class ListLongFilesMCPCommand(BaseMCPCommand):
    """
    MCP command to list files exceeding line limit.
    
    Equivalent to old code_mapper functionality for finding oversized files.
    """

    name = "list_long_files"
    version = "1.0.0"
    descr = "List files exceeding maximum line limit (code_mapper functionality)"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines threshold (default: 400)",
                    "default": 400,
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
        max_lines: int = 400,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list long files command.

        Args:
            root_dir: Root directory of the project
            max_lines: Maximum lines threshold
            project_id: Optional project UUID

        Returns:
            SuccessResult with long files list or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            
            if not proj_id:
                db.close()
                return ErrorResult(
                    message="Project not found",
                    code="PROJECT_NOT_FOUND",
                    details={"root_dir": str(root_path)},
                )

            command = ListLongFilesCommand(db, proj_id, max_lines)
            result = await command.execute()
            db.close()

            return SuccessResult(data=result)

        except Exception as e:
            return self._handle_error(e, "LIST_LONG_FILES_ERROR", "list_long_files")


class ListErrorsByCategoryMCPCommand(BaseMCPCommand):
    """
    MCP command to list errors grouped by category.
    
    Equivalent to old code_mapper functionality for listing code issues.
    """

    name = "list_errors_by_category"
    version = "1.0.0"
    descr = "List code errors grouped by category (code_mapper functionality)"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir (or all projects if not found)",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute list errors by category command.

        Args:
            root_dir: Root directory of the project
            project_id: Optional project UUID

        Returns:
            SuccessResult with errors grouped by category or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            
            # Try to get project_id, but allow None (all projects)
            proj_id = None
            if project_id:
                proj_id = project_id
            else:
                try:
                    proj_id = self._get_project_id(db, root_path, None)
                except Exception:
                    # If project not found, use None to get all projects
                    logger.info(f"Project not found for {root_dir}, listing errors from all projects")
                    proj_id = None

            command = ListErrorsByCategoryCommand(db, proj_id)
            result = await command.execute()
            db.close()

            return SuccessResult(data=result)

        except Exception as e:
            return self._handle_error(e, "LIST_ERRORS_ERROR", "list_errors_by_category")

