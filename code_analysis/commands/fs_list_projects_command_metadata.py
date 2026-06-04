"""
Metadata for fs_list_projects MCP command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type

from .command_metadata_helpers import build_command_metadata, simple_success_return


def get_fs_list_projects_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for fs_list_projects."""
    return build_command_metadata(
        cls,
        detailed_description=(
            "Filesystem project discovery without PostgreSQL or the projects registry.\n\n"
            "Algorithm (same as file watcher startup via "
            "``discover_projects_in_directory``):\n"
            "1. Load ``code_analysis.worker.watch_dirs`` from the server config file "
            "(each entry: ``id`` UUID + ``path``; relative paths resolve against the "
            "config directory).\n"
            "2. For each watch directory, list **direct child** directories only.\n"
            "3. Keep those with a valid ``projectid`` JSON file at "
            "``<watch_dir>/<name>/projectid`` (immediate child rule; deeper files are "
            "ignored).\n"
            "4. Return ``watch_dir_id``, watch path, ``project_id``, project name, "
            "relative segment under the watch dir, and absolute root path.\n\n"
            "Use when ``list_projects`` or ``list_watch_dirs`` fail because the shared "
            "database is unavailable. Does **not** register or mutate projects in the "
            "database; the file watcher performs registration on startup.\n\n"
            "Read-only: scans config and disk only. Safe when the database is down."
        ),
        usage_examples=[
            {
                "description": "Discover all projects under configured watch directories",
                "command": {},
                "explanation": (
                    "Returns watch_dir_id and project_id for every valid immediate-child "
                    "project directory. No parameters."
                ),
            },
            {
                "description": "Scan one configured watch directory",
                "command": {
                    "watch_dir_id": "a6c47e01-1ac8-47a6-a0e8-e6416086de0c",
                },
                "explanation": (
                    "Limits discovery to the matching ``id`` from "
                    "``code_analysis.worker.watch_dirs`` in config (not from list_watch_dirs)."
                ),
            },
        ],
        error_cases={
            "NO_WATCH_DIRS": {
                "description": "Config has no valid ``code_analysis.worker.watch_dirs`` entries.",
                "message": "No watch directories configured",
                "solution": (
                    "Add watch_dirs with ``id`` and ``path`` under "
                    "``code_analysis.worker`` in config.json and restart the server."
                ),
            },
            "WATCH_DIR_NOT_FOUND": {
                "description": (
                    "The ``watch_dir_id`` filter does not match any configured watch directory."
                ),
                "message": "Watch directory id not found in config: {watch_dir_id}",
                "solution": (
                    "Omit ``watch_dir_id`` or use an ``id`` from "
                    "``code_analysis.worker.watch_dirs`` in server config."
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
                "description": "Parameter validation failed (e.g. empty watch_dir_id string).",
                "message": "watch_dir_id must be a non-empty string when provided",
                "solution": "Fix params per get_schema() and retry.",
            },
            "FS_LIST_PROJECTS_ERROR": {
                "description": "Unexpected failure while reading config or scanning disk.",
                "message": "fs_list_projects failed",
                "solution": "Check server logs, config path, and watch directory permissions.",
            },
        },
        return_value=simple_success_return(
            description="Discovery completed; projects found on disk.",
            data_fields={
                "success": "True when the command completes without error.",
                "watch_dirs": (
                    "List of per watch-dir blocks: watch_dir_id, absolute_path, exists, "
                    "and nested projects."
                ),
                "projects": (
                    "Flat list of discovered projects with watch_dir_id, project_id, "
                    "name, root_path (segment under watch dir), root_path_absolute, "
                    "description, id (alias of project_id), comment (alias of description)."
                ),
                "count": "Number of entries in the flat projects list.",
            },
            example={
                "success": True,
                "watch_dirs": [
                    {
                        "watch_dir_id": "a6c47e01-1ac8-47a6-a0e8-e6416086de0c",
                        "absolute_path": "/home/user/tools",
                        "exists": True,
                        "projects": [
                            {
                                "watch_dir_id": "a6c47e01-1ac8-47a6-a0e8-e6416086de0c",
                                "watch_dir_path": "/home/user/tools",
                                "project_id": "dbd08d2c-4673-4ec6-b4c1-50fe84cc1269",
                                "id": "dbd08d2c-4673-4ec6-b4c1-50fe84cc1269",
                                "name": "code_analysis",
                                "root_path": "code_analysis",
                                "root_path_absolute": "/home/user/tools/code_analysis",
                                "description": "Code analysis server",
                                "comment": "Code analysis server",
                            }
                        ],
                    }
                ],
                "projects": [
                    {
                        "watch_dir_id": "a6c47e01-1ac8-47a6-a0e8-e6416086de0c",
                        "watch_dir_path": "/home/user/tools",
                        "project_id": "dbd08d2c-4673-4ec6-b4c1-50fe84cc1269",
                        "id": "dbd08d2c-4673-4ec6-b4c1-50fe84cc1269",
                        "name": "code_analysis",
                        "root_path": "code_analysis",
                        "root_path_absolute": "/home/user/tools/code_analysis",
                        "description": "Code analysis server",
                        "comment": "Code analysis server",
                    }
                ],
                "count": 1,
            },
        ),
        best_practices=[
            "Prefer list_projects when the database is healthy (includes registry metadata).",
            "Use fs_list_projects when SharedDatabaseNotInitializedError or list_projects "
            "times out; pair returned project_id with list_project_files or universal_file_open "
            "once the database is available again.",
            "watch_dir_id values come from config (code_analysis.worker.watch_dirs), not from "
            "list_watch_dirs (database registry).",
            "Read-only: does not create backups, modify disk, or write to the database.",
            "Project roots must be immediate children of the watch directory; deeper projectid "
            "files are ignored (same rule as the file watcher).",
        ],
    )
