"""
MCP command: list_projects (disk discovery from config watch dirs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.exceptions import DuplicateProjectIdError, ValidationError
from ...core.list_pagination import (
    build_list_page_payload,
    list_pagination_schema_properties,
    paginate_sequence,
    resolve_list_pagination,
)
from ...core.watch_dirs_from_config import (
    discovered_project_to_list_row,
    flatten_discovered_projects,
)
from ...core.watch_dirs_runtime import (
    discover_project_candidates_runtime,
    load_watch_dir_specs_runtime,
    runtime_has_watch_dirs,
)
from ._shared import BaseMCPCommand


class ListProjectsMCPCommand(BaseMCPCommand):
    """List projects by scanning configured watch directories (filesystem)."""

    name = "list_projects"
    version = "2.0.0"
    descr = (
        "List projects discovered under mounted watch directories (UUID4 children "
        "of watch_mount_root). Host prepare script materializes config/catalog first."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["ListProjectsMCPCommand"]) -> Dict[str, Any]:
        """Return the schema for watch-directory, project filters, and pagination."""
        pagination = list_pagination_schema_properties()
        return {
            "type": "object",
            "description": (
                "Discover projects on disk under ``file_watcher.watch_mount_root``. "
                "Only UUID4 immediate subdirectories count (same as file watcher). "
                "Config ``worker.watch_dirs`` is applied on the host by "
                "``casmgr-prepare-watch-mounts`` before server start. Paginated "
                "(default page_size 20); use ``block_position`` for the next page "
                "(same contract as ``search`` / ``list_project_files``)."
            ),
            "properties": {
                **pagination,
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
                {"page_size": 50, "block_position": 2},
            ],
        }

    @classmethod
    def metadata(cls: Type["ListProjectsMCPCommand"]) -> Dict[str, Any]:
        """Return registration metadata for filesystem project discovery."""
        from .list_projects_metadata import get_list_projects_metadata

        return get_list_projects_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize an optional configured watch-directory ID."""
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
            specs = load_watch_dir_specs_runtime(config_path)
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
        page_size: Optional[int] = None,
        block_position: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Discover projects on disk, apply filters, and return one page.

        Discovery itself is the cheap no-walk candidate pass (see
        ``discover_project_candidates_runtime`` /
        ``project_discovery.discover_project_candidates_in_directory``): it
        never runs the recursive ``validate_no_nested_projects`` walk, so cost
        is bounded by the number of immediate-child catalog entries, not by
        the size of any project's file tree. Pagination then slices the
        filtered, stably-sorted candidate list; no parameter combination
        forces a full-catalog scan of project internals.
        """
        try:
            params = self.validate_params(
                {
                    "watched_dir_id": watched_dir_id,
                    "name_contains": name_contains,
                    "comment_contains": comment_contains,
                    "include_deleted": include_deleted,
                    "page_size": page_size,
                    "block_position": block_position,
                    "limit": limit,
                    "offset": offset,
                    **kwargs,
                }
            )
            watched_dir_id = params.get("watched_dir_id")
            name_contains = params.get("name_contains")
            comment_contains = params.get("comment_contains")
            include_deleted = bool(params.get("include_deleted", False))

            config_path = self._resolve_config_path()
            try:
                watch_results = discover_project_candidates_runtime(
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
                specs = load_watch_dir_specs_runtime(config_path)
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
                if not runtime_has_watch_dirs(config_path):
                    return ErrorResult(
                        message="No watch directories mounted under watch_mount_root",
                        code="NO_WATCH_DIRS",
                        details={
                            "config_path": str(config_path),
                            "hint": (
                                "Run casmgr-prepare-watch-mounts on the host so config "
                                "worker.watch_dirs and host_watch_catalog appear as "
                                "UUID4 subdirectories of watch_mount_root"
                            ),
                        },
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

            # discover_project_candidates_runtime already returns a stable order
            # (sorted by lowercased directory name, project_id tie-break) per
            # watch dir; multiple watch dirs are concatenated in spec order, so
            # re-sort the merged, filtered list once here for a single global
            # stable order that pagination can safely page across.
            projects.sort(
                key=lambda p: (str(p.get("name") or "").lower(), str(p.get("id") or ""))
            )

            total = len(projects)
            page_size_r, offset_r, block_position_r = resolve_list_pagination(
                {
                    "page_size": page_size,
                    "block_position": block_position,
                    "limit": limit,
                    "offset": offset,
                }
            )
            page_items = paginate_sequence(
                projects, offset=offset_r, page_size=page_size_r
            )

            return SuccessResult(
                data=build_list_page_payload(
                    items=page_items,
                    total=total,
                    page_size=page_size_r,
                    block_position=block_position_r,
                    offset=offset_r,
                    legacy_items_key="projects",
                )
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
