"""
MCP command: list_projects (disk discovery from config watch dirs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.exceptions import DuplicateProjectIdError, ValidationError
from ...core.watch_dirs_from_config import (
    discover_projects_from_config,
    discovered_project_to_list_row,
    flatten_discovered_projects,
    load_watch_dir_specs_from_config,
)
from ._shared import BaseMCPCommand


class ListProjectsMCPCommand(BaseMCPCommand):
    """List projects by scanning configured watch directories (filesystem)."""

    name = "list_projects"
    version = "2.0.0"
    descr = (
        "List projects discovered on disk from configured watch directories. "
        "Reads projectid metadata; does not query the database."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ListProjectsMCPCommand"]) -> Dict[str, Any]:
        return {
            "type": "object",
            "description": (
                "Discover projects on disk from ``code_analysis.worker.watch_dirs`` in "
                "server config. Returns the standard list_projects project dict shape. "
                "By default excludes projects with ``projectid.deleted: true``."
            ),
            "properties": {
                "include_deleted": {
                    "type": "boolean",
                    "description": (
                        "If true, include projects whose ``projectid`` has "
                        "``deleted: true``. Default false."
                    ),
                    "default": False,
                },
                "watched_dir_id": {
                    "type": "string",
                    "description": (
                        "Optional watch directory UUID from "
                        "``code_analysis.worker.watch_dirs[].id`` in server config."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "name_contains": {
                    "type": "string",
                    "description": (
                        "Optional substring filter on project folder name (case-insensitive)."
                    ),
                    "examples": ["vast_srv", "code_analysis"],
                },
                "comment_contains": {
                    "type": "string",
                    "description": (
                        "Optional substring filter on projectid description (case-insensitive)."
                    ),
                    "examples": ["pipeline"],
                },
            },
            "required": [],
            "additionalProperties": False,
            "examples": [
                {},
                {"include_deleted": True},
                {"watched_dir_id": "550e8400-e29b-41d4-a716-446655440000"},
                {"name_contains": "vast_srv"},
                {"comment_contains": "pipeline"},
            ],
        }

    @classmethod
    def metadata(cls: Type["ListProjectsMCPCommand"]) -> Dict[str, Any]:
        from .list_projects_metadata import get_list_projects_metadata

        return get_list_projects_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        watched_dir_id = params.get("watched_dir_id")
        if watched_dir_id:
            wid = str(watched_dir_id).strip()
            if not wid:
                raise ValidationError(
                    "watched_dir_id must be a non-empty string when provided",
                    field="watched_dir_id",
                    details={},
                )
            config_path = self._resolve_config_path()
            specs = load_watch_dir_specs_from_config(config_path)
            if not any(s.watch_dir_id == wid for s in specs):
                raise ValidationError(
                    f"Watched directory not found: {wid}",
                    field="watched_dir_id",
                    details={"watched_dir_id": wid},
                )
            params["watched_dir_id"] = wid
        return params

    async def execute(
        self,
        watched_dir_id: Optional[str] = None,
        name_contains: Optional[str] = None,
        comment_contains: Optional[str] = None,
        include_deleted: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            params = self.validate_params(
                {
                    "watched_dir_id": watched_dir_id,
                    "name_contains": name_contains,
                    "comment_contains": comment_contains,
                    "include_deleted": include_deleted,
                    **kwargs,
                }
            )
            watched_dir_id = params.get("watched_dir_id")
            name_contains = params.get("name_contains")
            comment_contains = params.get("comment_contains")
            include_deleted = bool(params.get("include_deleted", False))

            config_path = self._resolve_config_path()
            try:
                watch_results = discover_projects_from_config(
                    config_path,
                    watch_dir_id=watched_dir_id,
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

            if watched_dir_id is not None and not watch_results:
                specs = load_watch_dir_specs_from_config(config_path)
                known_ids = {s.watch_dir_id for s in specs}
                if watched_dir_id not in known_ids:
                    return self._handle_error(
                        ValidationError(
                            f"Watched directory not found: {watched_dir_id}",
                            field="watched_dir_id",
                            details={"watched_dir_id": watched_dir_id},
                        ),
                        "INVALID_WATCHED_DIR_ID",
                        self.name,
                    )

            if not watch_results and watched_dir_id is None:
                if not load_watch_dir_specs_from_config(config_path):
                    return ErrorResult(
                        message="No watch directories configured",
                        code="NO_WATCH_DIRS",
                        details={"config_path": str(config_path)},
                    )

            flat = flatten_discovered_projects(watch_results)
            projects: List[Dict[str, Any]] = []
            for item in flat:
                if not include_deleted and item.deleted:
                    continue
                projects.append(discovered_project_to_list_row(item))

            if name_contains is not None:
                needle = name_contains.lower()
                projects = [
                    p
                    for p in projects
                    if str(p.get("name") or "").lower().find(needle) >= 0
                ]
            if comment_contains is not None:
                needle = comment_contains.lower()
                projects = [
                    p
                    for p in projects
                    if str(p.get("comment") or "").lower().find(needle) >= 0
                ]

            parts: List[str] = []
            if watched_dir_id:
                parts.append(f"watched_dir_id: {watched_dir_id}")
            if name_contains is not None:
                parts.append(f"name_contains: {name_contains!r}")
            if comment_contains is not None:
                parts.append(f"comment_contains: {comment_contains!r}")
            if include_deleted:
                parts.append("include_deleted: true")
            filter_msg = (" (filtered by " + ", ".join(parts) + ")") if parts else ""

            return SuccessResult(
                data={
                    "projects": projects,
                    "count": len(projects),
                },
                message=f"Found {len(projects)} project(s){filter_msg}",
            )
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            return self._handle_error(e, "LIST_PROJECTS_ERROR", self.name)
