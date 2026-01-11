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
    2. Walk up the directory tree towards watch_dir
    3. For each directory:
       a. Check if it's within any watch_dir
       b. If depth <= 1 (watch_dir or direct children), check for projectid file
       c. If depth > 1, skip projectid check but continue walking up
       d. If projectid found, validate no nested projects
       e. Return ProjectRoot if valid
    4. Stop when reaching watch_dir boundary or filesystem root

    Rule: projectid can be ONLY in watch_dir or direct children (max depth 1).
    - watch_dir/projectid - allowed (depth 0)
    - watch_dir/dirA/projectid - allowed (depth 1)
    - watch_dir/dirA/dirB/projectid - NOT allowed (depth 2 - too deep, ignored)
    
    Note: Files can be at ANY depth within a project. Only projectid location
    is restricted to depth 0-1. This function walks up from the file location
    to find the nearest valid projectid.

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
    # Rule: projectid can be ONLY at watch_dir (depth 0) or direct children (depth 1)
    # We scan ALL files recursively, but only check for projectid at depth 0-1
    search_path = current_dir
    
    while True:
        # Check if we've gone beyond the watch_dir
        try:
            relative_path = search_path.relative_to(containing_watch_dir)
        except ValueError:
            # We've gone beyond the watch_dir, no project found
            logger.debug(
                f"No project found for file {file_path} (reached watch_dir boundary)"
            )
            return None

        # Check depth: projectid can be ONLY at watch_dir (depth 0) or direct children (depth 1)
        # relative_path.parts is empty for watch_dir itself, length 1 for direct children
        depth = len(relative_path.parts)
        
        # Only check for projectid if we're at depth 0 or 1
        # If depth > 1, skip projectid check but continue walking up
        if depth <= 1:
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

        # Move up one level (always continue, even if depth > 1)
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
    Validate that no parent or child directory contains a projectid file.

    Algorithm:
    1. Walk up from project_root to watch_dir - check parent directories
    2. Scan down from project_root - check subdirectories for nested projectid files
    3. If found in either direction, raise NestedProjectError

    Args:
        project_root: Path to project root (contains projectid)
        watch_dir: Watched directory that contains this project

    Raises:
        NestedProjectError: If parent or child directory has projectid
    """
    project_root = Path(project_root).resolve()
    watch_dir = Path(watch_dir).resolve()
    main_projectid_path = project_root / "projectid"

    # 1. Check parent directories (walk UP from project_root.parent to watch_dir)
    current = project_root.parent
    while True:
        # Check if we've reached watch_dir or gone beyond it
        try:
            current.relative_to(watch_dir)
        except ValueError:
            # We've gone beyond watch_dir, no nested project in parent
            break

        # Check if this directory contains projectid file
        projectid_path = current / "projectid"
        if projectid_path.exists() and projectid_path.is_file():
            # Found nested project in parent directory
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

    # 2. Check subdirectories (scan DOWN from project_root for nested projectid files)
    try:
        for item in project_root.rglob("projectid"):
            if item.is_file() and item != main_projectid_path:
                # Found nested projectid in subdirectory
                nested_project_root = item.parent.resolve()
                raise NestedProjectError(
                    message=(
                        f"Nested project detected: {nested_project_root} contains projectid "
                        f"inside project {project_root}"
                    ),
                    child_project=str(nested_project_root),
                    parent_project=str(project_root),
                )
    except OSError as e:
        logger.warning(
            f"Error scanning for nested projects in {project_root}: {e}"
        )
        # Don't fail on scan errors, but log warning


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
    1. Scan watch_dir for projectid files ONLY at:
       - watch_dir/projectid (level 0)
       - watch_dir/dirA/projectid (level 1 - direct children only)
    2. For each projectid found:
       a. Load project_id from projectid file
       b. Validate no nested projects
       c. Create ProjectRoot object
    3. Validate no duplicate project_ids
    4. Return list of discovered projects

    Rule: projectid can be ONLY in watch_dir or direct children (max depth 1).
    - watch_dir/projectid - allowed (level 0)
    - watch_dir/dirA/projectid - allowed (level 1)
    - watch_dir/dirA/dirB/projectid - NOT allowed (level 2 - too deep)
    - Directory without projectid is NOT a project

    Args:
        watch_dir: Watched directory to scan

    Returns:
        List of ProjectRoot objects

    Raises:
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

    # Scan for projectid files ONLY in watch_dir and direct children (max depth 1)
    # Rule: projectid can be at:
    #   - watch_dir/projectid (level 0)
    #   - watch_dir/dirA/projectid (level 1)
    #   - NOT watch_dir/dirA/dirB/projectid (level 2 - too deep)
    try:
        # Check watch_dir itself (level 0)
        watch_dir_projectid = watch_dir / "projectid"
        if watch_dir_projectid.exists() and watch_dir_projectid.is_file():
            projectid_files.append(watch_dir_projectid)
        
        # Check direct children only (level 1)
        for item in watch_dir.iterdir():
            if item.is_dir():
                child_projectid = item / "projectid"
                if child_projectid.exists() and child_projectid.is_file():
                    projectid_files.append(child_projectid)
    except OSError as e:
        logger.error(f"Error scanning watch directory {watch_dir}: {e}")
        return []

    # Sort by depth (shallowest first) to process parent projects before nested ones
    projectid_files.sort(key=lambda p: len(p.parts))

    # Build list of all project roots for nested checking
    all_project_roots: List[Path] = [p.parent.resolve() for p in projectid_files]

    # Process each projectid file
    for projectid_path in projectid_files:
        project_root = projectid_path.parent.resolve()

        # Check if this project is nested inside any other project (from all found projectid files)
        # Rule: Only one projectid per branch (from watch_dir to any file)
        is_nested = False
        for other_project_root in all_project_roots:
            if other_project_root == project_root:
                continue  # Skip self
            try:
                # Check if project_root is inside other_project_root
                project_root.relative_to(other_project_root)
                # This project is nested inside another project - skip with error
                logger.error(
                    f"Nested project detected: {project_root} contains projectid "
                    f"inside project {other_project_root}. "
                    f"Only one projectid per branch is allowed. Skipping nested project {project_root}."
                )
                is_nested = True
                break
            except ValueError:
                # Not nested in this project, continue checking
                continue

        if is_nested:
            continue  # Skip this nested project

        try:
            # Load and validate project info
            from .project_resolution import load_project_info

            project_info = load_project_info(project_root)
            # Validate no nested projects in subdirectories
            # This checks if any subdirectory contains projectid (should not happen after above check,
            # but provides additional validation)
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
            # Check if nested project is in subdirectory (child) or parent
            nested_path = Path(e.child_project)
            if nested_path.is_relative_to(project_root) and nested_path != project_root:
                # Nested project in subdirectory - skip this project, log error
                logger.error(
                    f"Nested project detected in subdirectory: {e.child_project} "
                    f"contains projectid inside project {project_root}. "
                    f"Skipping project {project_root}."
                )
                continue  # Skip this project, continue with others
            else:
                # Nested project in parent - this should not happen after sorting,
                # but log error and skip
                logger.error(
                    f"Nested project detected: {e.child_project} is inside {e.parent_project}. "
                    f"Skipping project {project_root}."
                )
                continue  # Skip this project, continue with others

    # Validate no duplicate project_ids within this watch_dir
    validate_no_duplicate_project_ids(discovered_projects)

    return discovered_projects
