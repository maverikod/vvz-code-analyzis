"""
Metadata for list_projects MCP command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from ..command_metadata_helpers import build_command_metadata, simple_success_return


def get_list_projects_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for list_projects."""
    return build_command_metadata(
        cls,
        detailed_description=(
            "Discover projects on disk from configured watch directories.\n\n"
            "Reads ``code_analysis.worker.watch_dirs`` in server config, scans each "
            "watch directory's **immediate child** folders for a valid ``projectid`` "
            "file (same membership rule as the file watcher: immediate child + a "
            "``projectid`` file that parses). A subdirectory with no ``projectid`` "
            "file, or one whose ``projectid`` fails to parse, is simply not a "
            "project and is skipped -- never raises, never appears in the result.\n\n"
            "Discovery is a cheap pass only: one directory listing per watch dir "
            "plus one ``projectid`` read per candidate. It does **not** walk into "
            "any project's file tree, so cost does not scale with project size or "
            "count of files -- only with the number of top-level catalog entries.\n\n"
            "Paginated (search-aligned envelope): ``paginated: true``, ``items`` "
            "(canonical) and ``projects`` (legacy alias, same list) for the current "
            "page, plus ``count``, ``total``, ``page_size`` (default 20), "
            "``block_position`` (1-based, default 1), ``has_more``, ``offset``. Use "
            "``block_position`` (or legacy ``offset``/``limit``) to page through "
            "large catalogs instead of receiving every project in one response.\n\n"
            "Each project row: ``id``, ``watch_dir``, ``name``, ``root_path``, "
            "``comment``, ``watch_dir_id``, ``processing_paused``, ``deleted``, "
            "``updated_at``. ``deleted`` and ``processing_paused`` come from "
            "``projectid`` on disk. ``updated_at`` is always ``null`` here (the file "
            "watcher maintains it in the database during scans). Filters "
            "(``name_contains``, ``comment_contains``, ``include_deleted``, "
            "``watched_dir_id``) apply before pagination, so ``total`` always "
            "reflects the filtered set, not just the current page.\n\n"
            "Does not query or write the database. Read-only."
        ),
        usage_examples=[
            {
                "description": "List the first page (20) of active projects",
                "command": {},
                "explanation": (
                    "Returns page 1 of non-deleted projects discovered on disk. "
                    "Omits rows with ``projectid.deleted: true`` unless "
                    "``include_deleted`` is set. Check ``has_more``/``total`` to "
                    "decide whether to fetch another page."
                ),
            },
            {
                "description": "Fetch the next page",
                "command": {"page_size": 50, "block_position": 2},
                "explanation": (
                    "Rows 51-100 of the filtered, stably-sorted catalog "
                    "(sorted by project folder name, id tie-break)."
                ),
            },
            {
                "description": "Filter by configured watch directory id",
                "command": {
                    "watched_dir_id": "550e8400-e29b-41d4-a716-446655440000",
                },
                "explanation": (
                    "``watched_dir_id`` must match ``code_analysis.worker.watch_dirs[].id`` "
                    "in server config."
                ),
            },
            {
                "description": "Include soft-deleted projects from projectid",
                "command": {"include_deleted": True},
            },
            {
                "description": "Filter by project folder name",
                "command": {"name_contains": "code_analysis"},
            },
            {
                "description": "Filter by projectid description",
                "command": {"comment_contains": "pipeline"},
            },
        ],
        error_cases={
            "NO_WATCH_DIRS": {
                "description": (
                    "No watch dirs in config and none mounted under watch_mount_root."
                ),
                "message": "No watch directories configured or mounted",
                "solution": (
                    "Set ``host_watch_catalog`` / ``worker.watch_dirs`` in config, run "
                    "``casmgr-prepare-watch-mounts`` on the host, ensure UUID4 dirs "
                    "exist under ``watch_mount_root``, then restart the server."
                ),
            },
            "INVALID_WATCHED_DIR_ID": {
                "description": (
                    "``watched_dir_id`` does not match any configured watch directory."
                ),
                "message": "Watched directory not found: {watched_dir_id}",
                "solution": (
                    "Use an ``id`` from ``code_analysis.worker.watch_dirs`` in server config."
                ),
            },
            "DUPLICATE_PROJECT_ID": {
                "description": (
                    "Two project roots under the same watch directory share the same UUID."
                ),
                "message": "Duplicate project_id detected during discovery",
                "solution": (
                    "Fix ``projectid`` files so each project root has a unique ``id`` field."
                ),
            },
            "VALIDATION_ERROR": {
                "description": "Parameter validation failed.",
                "message": "Validation failed",
                "solution": "Fix params per get_schema() and retry.",
            },
            "LIST_PROJECTS_ERROR": {
                "description": "Unexpected failure while reading config or scanning disk.",
                "message": "list_projects failed",
                "solution": "Check server logs, config path, and watch directory permissions.",
            },
        },
        return_value=simple_success_return(
            description="Discovery completed; one page of the filtered catalog.",
            data_fields={
                "projects": (
                    "Current page of project dicts (legacy key, same list as ``items``): "
                    "id, watch_dir, name, root_path (segment under watch dir), comment, "
                    "watch_dir_id, processing_paused, deleted, updated_at (null on disk "
                    "discovery)."
                ),
                "items": "Same list as ``projects`` (canonical pagination key).",
                "paginated": "Always true.",
                "count": "Number of projects in this page.",
                "total": "Number of projects after filters, before pagination.",
                "page_size": "Rows per page actually used (default 20, max 200).",
                "block_position": "1-based page index actually used (default 1).",
                "has_more": "True when further pages remain after this one.",
                "offset": "Row offset actually used for this page.",
            },
            example={
                "paginated": True,
                "items": [
                    {
                        "id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "watch_dir": "/home/user/tools",
                        "name": "code_analysis",
                        "root_path": "code_analysis",
                        "comment": "Code analysis server",
                        "watch_dir_id": "550e8400-e29b-41d4-a716-446655440000",
                        "processing_paused": False,
                        "deleted": False,
                        "updated_at": None,
                    }
                ],
                "projects": [
                    {
                        "id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "watch_dir": "/home/user/tools",
                        "name": "code_analysis",
                        "root_path": "code_analysis",
                        "comment": "Code analysis server",
                        "watch_dir_id": "550e8400-e29b-41d4-a716-446655440000",
                        "processing_paused": False,
                        "deleted": False,
                        "updated_at": None,
                    }
                ],
                "count": 1,
                "total": 1,
                "page_size": 20,
                "block_position": 1,
                "has_more": False,
                "offset": 0,
            },
        ),
        best_practices=[
            "``watched_dir_id`` values come from config (``code_analysis.worker.watch_dirs``), "
            "not from ``list_watch_dirs`` (database registry).",
            "Project roots must be immediate children of the watch directory.",
            "For ``updated_at`` reflecting last file activity, use database status commands "
            "or wait for the file watcher to sync ``projects.updated_at``.",
            "Read-only: does not register projects in the database; the file watcher does that.",
            "Default page size is 20; on large catalogs, page with ``block_position`` "
            "(or legacy ``offset``/``limit``) instead of assuming one call returns "
            "every project.",
            "``total`` reflects the filtered set (after ``name_contains``, "
            "``comment_contains``, ``include_deleted``, ``watched_dir_id``), not the "
            "whole catalog.",
        ],
    )
