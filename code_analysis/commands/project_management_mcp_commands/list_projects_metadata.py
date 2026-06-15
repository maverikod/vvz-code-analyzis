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
            "file (same rules as the file watcher). Returns the same project dict "
            "shape as the former database-backed command: ``id``, ``watch_dir``, "
            "``name``, ``root_path``, ``comment``, ``watch_dir_id``, "
            "``processing_paused``, ``deleted``, ``updated_at``.\n\n"
            "``deleted`` and ``processing_paused`` come from ``projectid`` on disk. "
            "``updated_at`` is always ``null`` here (the file watcher maintains it in "
            "the database during scans).\n\n"
            "Does not query or write the database. Read-only."
        ),
        usage_examples=[
            {
                "description": "List active projects under all configured watch dirs",
                "command": {},
                "explanation": (
                    "Returns non-deleted projects discovered on disk. "
                    "Omits rows with ``projectid.deleted: true`` unless "
                    "``include_deleted`` is set."
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
            description="Discovery completed.",
            data_fields={
                "projects": (
                    "List of project dicts: id, watch_dir, name, root_path (segment under "
                    "watch dir), comment, watch_dir_id, processing_paused, deleted, "
                    "updated_at (null on disk discovery)."
                ),
                "count": "Number of projects after filters.",
            },
            example={
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
            },
        ),
        best_practices=[
            "``watched_dir_id`` values come from config (``code_analysis.worker.watch_dirs``), "
            "not from ``list_watch_dirs`` (database registry).",
            "Project roots must be immediate children of the watch directory.",
            "For ``updated_at`` reflecting last file activity, use database status commands "
            "or wait for the file watcher to sync ``projects.updated_at``.",
            "Read-only: does not register projects in the database; the file watcher does that.",
        ],
    )
