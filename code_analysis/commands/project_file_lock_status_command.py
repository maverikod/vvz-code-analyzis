"""
MCP command: project_file_lock_status — DB advisory lock state for one file.

``file_path`` is resolved under the registered project's ``root_path`` (watched tree
from ``list_projects``), not under the code-analysis server package root.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .base_mcp_command_resolve_path import resolve_under_project_root
from .project_file_lock_status_metadata import get_project_file_lock_status_metadata
from .project_file_lock_status_schema import get_project_file_lock_status_schema
from ..core.exceptions import ValidationError
from ..core.runtime_lock_sessions import get_file_advisory_lock_status

logger = logging.getLogger(__name__)


class ProjectFileLockStatusCommand(BaseMCPCommand):
    """Read-only advisory lease status for a project file."""

    name = "project_file_lock_status"
    version = "1.0.0"
    descr = (
        "Return cooperative DB advisory lock state for a file (free / write_locked / "
        "fully_locked). file_path is relative to the registered watched project's root_path "
        "(list_projects), not the analysis server install root."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_lock_status_schema())

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        if not str(params.get("file_path") or "").strip():
            raise ValidationError(
                "file_path is required",
                field="file_path",
                details={},
            )
        return params

    @classmethod
    def metadata(cls: Type["ProjectFileLockStatusCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_lock_status_metadata(cls))

    async def execute(
        self, project_id: str, file_path: str, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        database = self._open_database_from_config(auto_analyze=False)
        try:
            project = database.get_project(project_id)
            if not project:
                return ErrorResult(
                    message=f"Project not found: {project_id}",
                    code="PROJECT_NOT_FOUND",
                    details={"project_id": project_id},
                )
            root = Path(project.root_path).resolve()
            try:
                abs_path = resolve_under_project_root(
                    root,
                    file_path,
                    require_exists=True,
                    must_be_file=True,
                )
            except ValidationError as exc:
                return ErrorResult(
                    message=str(exc),
                    code="FILE_NOT_FOUND",
                    details=getattr(exc, "details", None) or {},
                )

            rel_key = abs_path.resolve().relative_to(root).as_posix()
            payload = get_file_advisory_lock_status(
                database,
                project_id=project_id,
                file_path=rel_key,
            )
            return SuccessResult(data=payload)
        except Exception as e:
            logger.exception("project_file_lock_status failed")
            return ErrorResult(
                message=str(e),
                code="INTERNAL_ERROR",
                details={"error_type": type(e).__name__},
            )
        finally:
            database.disconnect()
