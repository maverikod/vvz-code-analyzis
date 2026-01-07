"""
Internal commands for project deletion.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase
else:
    CodeDatabase = Any

logger = logging.getLogger(__name__)


class DeleteProjectCommand:
    """
    Command to delete a project and all its data.

    This command completely removes a project from the database:
    - All files and their associated data (classes, functions, methods, etc.)
    - All chunks and vector indexes
    - All duplicates
    - All datasets
    - The project record itself

    Use with caution - this operation cannot be undone.
    """

    def __init__(
        self,
        database: CodeDatabase,
        project_id: str,
        dry_run: bool = False,
    ):
        """
        Initialize delete project command.

        Args:
            database: CodeDatabase instance
            project_id: Project ID to delete
            dry_run: If True, only show what would be deleted
        """
        self.database = database
        self.project_id = project_id
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project deletion.

        Returns:
            Dictionary with deletion results
        """
        # Get project info before deletion
        project = self.database.get_project(self.project_id)
        if not project:
            return {
                "success": False,
                "error": "PROJECT_NOT_FOUND",
                "message": f"Project {self.project_id} not found",
            }

        project_name = project.get("name", "Unknown")
        root_path = project.get("root_path", "Unknown")

        # Get statistics before deletion
        file_count = len(
            self.database.get_project_files(self.project_id, include_deleted=True)
        )

        # Count chunks
        chunk_count_row = self.database._fetchone(
            """
            SELECT COUNT(*) as count 
            FROM code_chunks cc
            JOIN files f ON cc.file_id = f.id
            WHERE f.project_id = ?
            """,
            (self.project_id,),
        )
        chunk_count = chunk_count_row["count"] if chunk_count_row else 0

        # Count datasets
        datasets = self.database.get_project_datasets(self.project_id)
        dataset_count = len(datasets)

        if self.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "project_id": self.project_id,
                "project_name": project_name,
                "root_path": root_path,
                "files_count": file_count,
                "chunks_count": chunk_count,
                "datasets_count": dataset_count,
                "message": f"Would delete project {project_name} ({self.project_id})",
            }

        # Perform deletion
        try:
            await self.database.clear_project_data(self.project_id)
            logger.info(
                f"Deleted project {self.project_id} ({project_name}): "
                f"{file_count} files, {chunk_count} chunks, {dataset_count} datasets"
            )
            return {
                "success": True,
                "dry_run": False,
                "project_id": self.project_id,
                "project_name": project_name,
                "root_path": root_path,
                "files_count": file_count,
                "chunks_count": chunk_count,
                "datasets_count": dataset_count,
                "message": f"Deleted project {project_name} ({self.project_id})",
            }
        except Exception as e:
            logger.error(
                f"Failed to delete project {self.project_id}: {e}", exc_info=True
            )
            return {
                "success": False,
                "error": "DELETION_ERROR",
                "message": f"Failed to delete project: {str(e)}",
                "project_id": self.project_id,
            }


class DeleteUnwatchedProjectsCommand:
    """
    Command to delete projects that are not in the list of watched directories.

    This command:
    1. Discovers all projects in watched directories using project discovery
    2. Finds all projects in the database
    3. Identifies projects that are not in the discovered list
    4. Deletes those projects

    Use with caution - this operation cannot be undone.
    """

    def __init__(
        self,
        database: CodeDatabase,
        watched_dirs: List[str],
        dry_run: bool = False,
        server_root_dir: Optional[str] = None,
    ):
        """
        Initialize delete unwatched projects command.

        Args:
            database: CodeDatabase instance
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
        all_projects = self.database._fetchall(
            "SELECT id, root_path, name FROM projects"
        )

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

            # Check if project is in discovered projects
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
                projects_to_delete.append(
                    {
                        "project_id": project_id,
                        "root_path": root_path,
                        "name": project_name,
                        "reason": "not_discovered_in_watch_dirs",
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
                    await self.database.clear_project_data(project_id)
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
