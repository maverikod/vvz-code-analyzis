"""
Project discovery module for automatic project detection.

This module implements automatic project discovery by finding `projectid` files
in the directory tree. Projects are identified by the presence of a `projectid`
file containing a UUID4 identifier.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .exceptions import (
    DuplicateProjectIdError,
    NestedProjectError,
    ProjectIdError,
)
from .project_resolution import load_project_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectRoot:
    """
    Represents a discovered project root.

    Attributes:
        root_path: Absolute path to project root directory (contains projectid file)
        project_id: Project ID (UUID4 string) loaded from projectid file
        description: Human-readable description of the project
        watch_dir: The watch_dir that contains this project (absolute path)
    """

    root_path: Path
    project_id: str
    description: str
    watch_dir: Path


def find_project_root(file_path: Path, watch_dirs: List[Path]) -> Optional[ProjectRoot]:
    """
    Find the project root for a given file by walking up the directory tree.

    Algorithm:
    1. Start from file_path's parent directory
    2. Walk up the directory tree
    3. For each directory:
       a. Check if it's within any watch_dir
       b. Check if it contains projectid file
       c. If found, validate no nested projects
       d. Return ProjectRoot if valid
    4. Stop when reaching watch_dir boundary or filesystem root

    Args:
        file_path: Path to file
        watch_dirs: List of watched directories (absolute paths)

    Returns:
        ProjectRoot if found, None otherwise

    Raises:
        NestedProjectError: If nested projects detected
    """
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        logger.warning(f"File does not exist: {file_path}")
        return None

    # Start from file's parent directory
    current_dir = file_path.parent.resolve()

    # Find which watch_dir contains this file (if any)
    containing_watch_dir: Optional[Path] = None
    for watch_dir in watch_dirs:
        watch_dir_resolved = Path(watch_dir).resolve()
        try:
            # Check if file is within this watch_dir
            current_dir.relative_to(watch_dir_resolved)
            containing_watch_dir = watch_dir_resolved
            break
        except ValueError:
            # File is not within this watch_dir
            continue

    if containing_watch_dir is None:
        logger.debug(f"File {file_path} is not within any watched directory, skipping")
        return None

    # Walk up from file's parent to watch_dir
    # Stop at watch_dir (don't go beyond it)
    search_path = current_dir
    while True:
        # Check if we've gone beyond the watch_dir
        try:
            search_path.relative_to(containing_watch_dir)
        except ValueError:
            # We've gone beyond the watch_dir, no project found
            logger.debug(
                f"No project found for file {file_path} (reached watch_dir boundary)"
            )
            return None

        # Check if this directory contains projectid file
        projectid_path = search_path / "projectid"
        if projectid_path.exists() and projectid_path.is_file():
            try:
                # Load and validate project info
                from .project_resolution import load_project_info

                project_info = load_project_info(search_path)
                # Validate no nested projects
                validate_no_nested_projects(search_path, containing_watch_dir)
                # Found valid project root
                return ProjectRoot(
                    root_path=search_path,
                    project_id=project_info.project_id,
                    description=project_info.description,
                    watch_dir=containing_watch_dir,
                )
            except ProjectIdError as e:
                logger.warning(
                    f"Invalid projectid file at {projectid_path}: {e}, skipping"
                )
                # Continue searching up the tree
            except NestedProjectError:
                # Re-raise nested project error
                raise

        # Move up one level
        parent = search_path.parent
        if parent == search_path:
            # Reached filesystem root
            break
        search_path = parent

    # No project found
    logger.debug(f"No project found for file {file_path}")
    return None


def validate_no_nested_projects(project_root: Path, watch_dir: Path) -> None:
    """
    Validate that no parent directory contains a projectid file.

    Algorithm:
    1. Walk up from project_root to watch_dir
    2. Check each parent directory for projectid file
    3. If found, raise NestedProjectError

    Args:
        project_root: Path to project root (contains projectid)
        watch_dir: Watched directory that contains this project

    Raises:
        NestedProjectError: If parent directory has projectid
    """
    project_root = Path(project_root).resolve()
    watch_dir = Path(watch_dir).resolve()

    # Walk up from project_root's parent to watch_dir
    current = project_root.parent
    while True:
        # Check if we've reached watch_dir or gone beyond it
        try:
            current.relative_to(watch_dir)
        except ValueError:
            # We've gone beyond watch_dir, no nested project
            break

        # Check if this directory contains projectid file
        projectid_path = current / "projectid"
        if projectid_path.exists() and projectid_path.is_file():
            # Found nested project
            raise NestedProjectError(
                message=f"Nested projects detected: {project_root} is inside {current}",
                child_project=str(project_root),
                parent_project=str(current),
            )

        # Move up one level
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent


def validate_no_duplicate_project_ids(
    discovered_projects: List[ProjectRoot],
) -> None:
    """
    Validate that no duplicate project_id exists in discovered projects.

    One project_id cannot be used in different directories.

    Args:
        discovered_projects: List of discovered ProjectRoot objects

    Raises:
        DuplicateProjectIdError: If duplicate project_id detected
    """
    project_id_map: dict[str, ProjectRoot] = {}
    for project in discovered_projects:
        existing = project_id_map.get(project.project_id)
        if existing:
            if existing.root_path != project.root_path:
                raise DuplicateProjectIdError(
                    message=(
                        f"Duplicate project_id {project.project_id} detected: "
                        f"already used in {existing.root_path}, found again in {project.root_path}"
                    ),
                    project_id=project.project_id,
                    existing_root=str(existing.root_path),
                    duplicate_root=str(project.root_path),
                )
        else:
            project_id_map[project.project_id] = project


def discover_projects_in_directory(watch_dir: Path) -> List[ProjectRoot]:
    """
    Discover all projects within a watched directory.

    Algorithm:
    1. Scan watch_dir recursively for projectid files
    2. For each projectid found:
       a. Validate no nested projects
       b. Load project_id from projectid file
       c. Create ProjectRoot object
    3. Validate no duplicate project_ids
    4. Return list of discovered projects

    Args:
        watch_dir: Watched directory to scan

    Returns:
        List of ProjectRoot objects

    Raises:
        NestedProjectError: If nested projects detected
        DuplicateProjectIdError: If duplicate project_id detected
    """
    watch_dir = Path(watch_dir).resolve()
    if not watch_dir.exists() or not watch_dir.is_dir():
        logger.warning(
            f"Watch directory does not exist or is not a directory: {watch_dir}"
        )
        return []

    discovered_projects: List[ProjectRoot] = []
    projectid_files: List[Path] = []

    # Scan recursively for projectid files
    try:
        for item in watch_dir.rglob("projectid"):
            if item.is_file():
                projectid_files.append(item)
    except OSError as e:
        logger.error(f"Error scanning watch directory {watch_dir}: {e}")
        return []

    # Process each projectid file
    for projectid_path in projectid_files:
        project_root = projectid_path.parent.resolve()

        try:
            # Load and validate project info
            from .project_resolution import load_project_info

            project_info = load_project_info(project_root)
            # Validate no nested projects
            validate_no_nested_projects(project_root, watch_dir)
            # Create ProjectRoot
            project = ProjectRoot(
                root_path=project_root,
                project_id=project_info.project_id,
                description=project_info.description,
                watch_dir=watch_dir,
            )
            discovered_projects.append(project)
            logger.debug(
                f"Discovered project: {project.project_id} at {project.root_path}"
            )
        except ProjectIdError as e:
            logger.warning(f"Invalid projectid file at {projectid_path}: {e}, skipping")
            continue
        except NestedProjectError as e:
            logger.error(
                f"Nested project detected: {e.child_project} is inside {e.parent_project}"
            )
            # Re-raise to stop processing
            raise

    # Validate no duplicate project_ids within this watch_dir
    validate_no_duplicate_project_ids(discovered_projects)

    return discovered_projects
