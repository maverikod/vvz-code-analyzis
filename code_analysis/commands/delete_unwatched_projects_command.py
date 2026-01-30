"""
Internal command to delete projects not in watched directories.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class DeleteUnwatchedProjectsCommand:
    """
    Command to delete only orphaned project records (root_path no longer on disk).

    All file-operating commands must work only within watched directories. The only
    exception is deletion commands that move to trash. This command does NOT delete
    projects that exist on disk but are outside watch_dirs — it only removes DB
    records for projects whose root_path does not exist (invalid_path or
    root_path_not_exists_on_disk). Projects "exists_on_disk_but_not_in_watch_dirs"
    are kept.

    Steps:
    1. Discover all projects in watched directories
    2. Find all projects in the database
    3. Mark for deletion only: invalid_path, root_path_not_exists_on_disk
    4. Delete those project records from the database

    Use with caution - this operation cannot be undone.
    """

    def __init__(
        self,
        database: DatabaseClient,
        watched_dirs: List[str],
        dry_run: bool = False,
        server_root_dir: Optional[str] = None,
    ):
        """
        Initialize delete unwatched projects command.

        Args:
            database: DatabaseClient instance
            watched_dirs: List of watched directory paths (absolute)
            dry_run: If True, only show what would be deleted
            server_root_dir: Server root directory (will be protected from deletion)
        """
        self.database = database
        self.watched_dirs = {Path(d).resolve() for d in watched_dirs}
        self.dry_run = dry_run
        self.server_root_dir = (
            Path(server_root_dir).resolve() if server_root_dir else None
        )

    async def execute(self) -> Dict[str, Any]:
        """
        Execute deletion of unwatched projects.

        Uses project discovery to find all projects in watched directories,
        then compares with database projects to find unwatched ones.

        Returns:
            Dictionary with deletion results
        """
        from ..core.project_discovery import (
            discover_projects_in_directory,
            NestedProjectError,
            DuplicateProjectIdError,
        )

        from .clear_project_data_impl import _clear_project_data_impl

        # Step 1: Discover all projects in watched directories
        discovered_project_ids: Set[str] = set()
        discovery_errors = []

        for watched_dir in self.watched_dirs:
            try:
                discovered_projects = discover_projects_in_directory(watched_dir)
                discovered_project_ids.update(p.project_id for p in discovered_projects)
                logger.debug(
                    f"Discovered {len(discovered_projects)} project(s) in {watched_dir}"
                )
            except NestedProjectError as e:
                logger.error(f"Nested project error in {watched_dir}: {e}")
                discovery_errors.append(f"Nested project in {watched_dir}: {e}")
            except DuplicateProjectIdError as e:
                logger.error(f"Duplicate project_id error in {watched_dir}: {e}")
                discovery_errors.append(f"Duplicate project_id in {watched_dir}: {e}")
            except Exception as e:
                logger.error(f"Error discovering projects in {watched_dir}: {e}")
                discovery_errors.append(f"Error in {watched_dir}: {e}")

        # Step 2: Get all projects from database
        result = self.database.execute("SELECT id, root_path, name FROM projects")
        # Handle different result formats
        if isinstance(result, list):
            all_projects = result
        elif isinstance(result, dict):
            all_projects = result.get("data", [])
        else:
            all_projects = []

        projects_to_delete = []
        projects_to_keep = []

        # Step 3: Compare database projects with discovered projects
        for project in all_projects:
            project_id = project["id"]
            root_path = project["root_path"]
            project_name = project.get("name", "Unknown")

            # Normalize project root path
            try:
                project_path = Path(root_path).resolve()
            except Exception as e:
                logger.warning(f"Invalid project path {root_path}: {e}")
                # If path is invalid, consider it unwatched
                projects_to_delete.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "invalid_path",
                    }
                )
                continue

            # Protect server root directory from deletion
            if self.server_root_dir and project_path == self.server_root_dir:
                projects_to_keep.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "server_root_protected",
                    }
                )
                continue

            # Check if project root path exists on disk
            if not project_path.exists():
                # Project root doesn't exist on disk - mark for deletion
                projects_to_delete.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "root_path_not_exists_on_disk",
                    }
                )
                continue

            # Check if project is in discovered projects (in watched directories)
            if project_id in discovered_project_ids:
                projects_to_keep.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "discovered_in_watch_dirs",
                    }
                )
            else:
                # Project exists on disk but is not in watched directories — keep it.
                # File-operating commands work only within watched dirs; we do not
                # delete projects outside watch_dirs (only orphaned DB records).
                projects_to_keep.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "exists_on_disk_but_not_in_watch_dirs",
                    }
                )

        if not projects_to_delete:
            return {
                "success": True,
                "dry_run": self.dry_run,
                "deleted_count": 0,
                "kept_count": len(projects_to_keep),
                "projects_deleted": [],
                "projects_kept": projects_to_keep,
                "message": "No unwatched projects found",
            }

        # Delete projects
        deleted_projects = []
        errors = []

        for project_info in projects_to_delete:
            project_id = project_info["project_id"]

            if self.dry_run:
                deleted_projects.append(project_info)
            else:
                try:
                    await _clear_project_data_impl(self.database, project_id)
                    deleted_projects.append(project_info)
                    logger.info(
                        f"Deleted unwatched project {project_info['name']} "
                        f"({project_id}): {project_info['root_path']}"
                    )
                except Exception as e:
                    error_info = {
                        "project_id": project_id,
                        "root_path": project_info["root_path"],
                        "name": project_info["name"],
                        "error": str(e),
                    }
                    errors.append(error_info)
                    logger.error(
                        f"Failed to delete project {project_id}: {e}",
                        exc_info=True,
                    )

        return {
            "success": len(errors) == 0 and len(discovery_errors) == 0,
            "dry_run": self.dry_run,
            "deleted_count": len(deleted_projects),
            "kept_count": len(projects_to_keep),
            "projects_deleted": deleted_projects,
            "projects_kept": projects_to_keep,
            "discovery_errors": discovery_errors if discovery_errors else None,
            "errors": errors if errors else None,
            "message": (
                f"Deleted {len(deleted_projects)} unwatched project(s), "
                f"kept {len(projects_to_keep)} watched project(s)"
            ),
        }
