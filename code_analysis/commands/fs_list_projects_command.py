"""
MCP command: fs_list_projects

Discover projects on disk from configured watch directories (no database).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import DuplicateProjectIdError, ValidationError
from ..core.watch_dirs_from_config import (
    discover_projects_from_config,
    flatten_discovered_projects,
    load_watch_dir_specs_from_config,
)
from .base_mcp_command import BaseMCPCommand


class FsListProjectsCommand(BaseMCPCommand):
    """List projects by scanning watch directories from config (filesystem only)."""

    name = "fs_list_projects"
    version = "1.0.0"
    descr = (
        "Discover projects on disk from configured watch directories. "
        "Reads ``code_analysis.worker.watch_dirs`` from server config, scans each "
        "watch dir's immediate subdirectories for a valid ``projectid`` file, and "
        "returns ``watch_dir_id`` plus ``project_id``. Does not use the database."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": (
                "Discover projects on disk from ``code_analysis.worker.watch_dirs`` in "
                "server config. Scans immediate subdirectories of each watch path for a "
                "valid ``projectid`` file. Does not query or write the database."
            ),
            "properties": {
                "watch_dir_id": {
                    "type": "string",
                    "description": (
                        "Optional watch directory UUID from "
                        "``code_analysis.worker.watch_dirs[].id`` in server config. "
                        "When set, only that watch directory is scanned."
                    ),
                    "examples": ["a6c47e01-1ac8-47a6-a0e8-e6416086de0c"],
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["FsListProjectsCommand"]) -> Dict[str, Any]:
        from .fs_list_projects_command_metadata import get_fs_list_projects_metadata

        return get_fs_list_projects_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        watch_dir_id = params.get("watch_dir_id")
        if watch_dir_id is not None:
            wid = str(watch_dir_id).strip()
            if not wid:
                raise ValidationError(
                    "watch_dir_id must be a non-empty string when provided",
                    field="watch_dir_id",
                    details={},
                )
            params["watch_dir_id"] = wid
        return params

    async def execute(
        self,
        watch_dir_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            params = self.validate_params({"watch_dir_id": watch_dir_id, **kwargs})
            watch_dir_id = params.get("watch_dir_id")
            config_path = self._resolve_config_path()
            try:
                watch_results = discover_projects_from_config(
                    config_path,
                    watch_dir_id=watch_dir_id,
                )
            except DuplicateProjectIdError as e:
                return ErrorResult(
                    message=str(e),
                    code="DUPLICATE_PROJECT_ID",
                    details={
                        "project_id": getattr(e, "project_id", None),
                        "existing_root": getattr(e, "existing_root", None),
                        "duplicate_root": getattr(e, "duplicate_root", None),
                    },
                )

            if watch_dir_id is not None and not watch_results:
                specs = load_watch_dir_specs_from_config(config_path)
                known_ids = {s.watch_dir_id for s in specs}
                if watch_dir_id not in known_ids:
                    return ErrorResult(
                        message=f"Watch directory id not found in config: {watch_dir_id!r}",
                        code="WATCH_DIR_NOT_FOUND",
                        details={"watch_dir_id": watch_dir_id},
                    )

            if not watch_results and watch_dir_id is None:
                if not load_watch_dir_specs_from_config(config_path):
                    return ErrorResult(
                        message="No watch directories configured",
                        code="NO_WATCH_DIRS",
                        details={"config_path": str(config_path)},
                    )

            flat = flatten_discovered_projects(watch_results)
            projects_payload: List[Dict[str, Any]] = []
            for item in flat:
                row = asdict(item)
                row["id"] = item.project_id
                row["comment"] = item.description
                projects_payload.append(row)

            watch_dirs_payload = [
                {
                    "watch_dir_id": block.watch_dir_id,
                    "absolute_path": block.absolute_path,
                    "exists": block.exists,
                    "projects": [
                        {
                            **asdict(p),
                            "id": p.project_id,
                            "comment": p.description,
                        }
                        for p in block.projects
                    ],
                }
                for block in watch_results
            ]

            return SuccessResult(
                data={
                    "success": True,
                    "watch_dirs": watch_dirs_payload,
                    "projects": projects_payload,
                    "count": len(projects_payload),
                },
                message=f"Discovered {len(projects_payload)} project(s) on disk",
            )
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            return self._handle_error(e, "FS_LIST_PROJECTS_ERROR", "fs_list_projects")
