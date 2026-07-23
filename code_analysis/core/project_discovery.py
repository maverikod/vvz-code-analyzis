"""
Project discovery module for automatic project detection.

Invariant (watch boundary): a ``projectid`` file is recognized **only** under
``<watch_dir>/<single_subdirectory>/projectid`` — i.e. the project root must be
an **immediate child** of a watched directory. There is no separate project for
``watch_dir/projectid`` (watch root is never a project) nor for
``watch_dir/a/b/.../projectid`` when ``b`` is deeper than one segment under
``watch_dir``; such deeper files are ignored for discovery (see
``validate_no_nested_projects`` logging; nested scan uses watcher directory
pruning, not blind ``rglob``). Files anywhere under a valid project
root still resolve to that root via ``find_project_root``.

Projects are identified by a ``projectid`` file containing a UUID4 identifier.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .exceptions import (
    DuplicateProjectIdError,
    InvalidProjectIdFormatError,
    NestedProjectError,
    ProjectIdError,
)
from .fs_permissions import log_walk_error

logger = logging.getLogger(__name__)


def is_immediate_child_project_dir(dir_path: Path, watch_dir: Path) -> bool:
    """
    True if dir_path is exactly one directory level below watch_dir.

    Project roots are only recognized here: watch_dir/<subdir>/projectid,
    not watch_dir/projectid and not deeper paths.
    """
    d = Path(dir_path).resolve()
    w = Path(watch_dir).resolve()
    try:
        rel = d.relative_to(w)
    except ValueError:
        return False
    return len(rel.parts) == 1


@dataclass(frozen=True, slots=True)
class ProjectRoot:
    """
    Represents a discovered project root.

    Attributes:
        root_path: Absolute path to project root directory (contains projectid file)
        project_id: Project ID (UUID4 string) loaded from projectid file
        description: Human-readable description of the project
        watch_dir: The watch_dir that contains this project (absolute path)
        deleted: ``projectid.deleted`` flag, when already loaded by the caller
            (cheap candidate discovery populates this from its single
            ``load_project_info`` read; default False for callers that never
            set it).
        processing_paused: ``projectid.processing_paused`` flag, same sourcing
            as ``deleted``.
    """

    root_path: Path
    project_id: str
    description: str
    watch_dir: Path
    deleted: bool = False
    processing_paused: bool = False


def find_project_root(file_path: Path, watch_dirs: List[Path]) -> Optional[ProjectRoot]:
    """
    Find the project root for a given file by walking up the directory tree.

    Algorithm:
    1. Start from file_path's parent directory
    2. Walk up the directory tree towards watch_dir
    3. For each directory on the path:
       a. Ensure it is still inside containing_watch_dir
       b. **Only** when relative depth under watch_dir is exactly **1**, check for
          ``projectid`` (that directory is the only level that may host a project root)
       c. At deeper relative depths, do not treat ``projectid`` as a root; keep walking up
       d. If a valid ``projectid`` is found at depth 1, validate via
          ``validate_no_nested_projects`` then return ``ProjectRoot``
    4. Stop when reaching watch_dir boundary or filesystem root

    Rule: a project root is ONLY ``watch_dir/<one_segment>/`` with a valid
    ``projectid`` file (immediate child of the watched directory).
    - watch_dir/prj/projectid — allowed
    - watch_dir/projectid — not a project root (watch root itself is never a project)
    - watch_dir/prj/sub/projectid — ignored as a separate project; files under
      ``prj/`` still resolve to ``watch_dir/prj`` if that directory has ``projectid``

    Files may live at any depth under such a project directory.

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

    # Walk up from file's parent to watch_dir; only immediate children of
    # containing_watch_dir may host projectid (exactly one path segment).
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

        depth = len(relative_path.parts)

        # Only watch_dir/<subdir>/ may contain projectid (depth must be exactly 1)
        if depth == 1:
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
                except (ProjectIdError, InvalidProjectIdFormatError) as e:
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

        # Enclosing project: only if parent dir is a valid project root
        # (immediate child of watch_dir with projectid), not watch_dir itself.
        projectid_path = current / "projectid"
        if (
            projectid_path.exists()
            and projectid_path.is_file()
            and is_immediate_child_project_dir(current, watch_dir)
        ):
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

    # 2. Deeper projectid files are not separate projects; log only (do not fail).
    # Use the same directory pruning as the file watcher (no rglob into test_data/trash).
    from .file_watcher_pkg.scanner import should_skip_dir

    try:
        walk_root = project_root.resolve()
    except OSError:
        walk_root = project_root
    try:
        for dirpath, dirnames, filenames in os.walk(
            walk_root, topdown=True, followlinks=False, onerror=log_walk_error
        ):
            dpath = Path(dirpath)
            pruned: List[str] = []
            for d in sorted(dirnames):
                child_dir = dpath / d
                if should_skip_dir(child_dir, walk_root=walk_root):
                    continue
                pruned.append(d)
            dirnames[:] = pruned
            if "projectid" not in filenames:
                continue
            item = dpath / "projectid"
            if item.is_file() and item != main_projectid_path:
                nested_project_root = dpath.resolve()
                logger.warning(
                    "Ignoring projectid below project root (not a separate project): %s "
                    "(project root %s)",
                    nested_project_root,
                    project_root,
                )
    except OSError as e:
        logger.warning(f"Error scanning for nested projects in {project_root}: {e}")


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
    1. Scan watch_dir for projectid files ONLY under immediate subdirectories:
       ``watch_dir/<subdir>/projectid`` (not ``watch_dir/projectid``).
    2. For each projectid found:
       a. Load project_id from projectid file
       b. Validate no nested projects
       c. Create ProjectRoot object
    3. Validate no duplicate project_ids
    4. Return list of discovered projects

    Rule: projectid must be only in immediate children of watch_dir.
    - watch_dir/dirA/projectid — allowed
    - watch_dir/projectid — ignored (watch root is not a project)
    - watch_dir/dirA/dirB/projectid — not discovered as a project
    - Directory without valid projectid is NOT a project

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

    # Only watch_dir/<subdir>/projectid (immediate children of watch_dir)
    try:
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
        except (ProjectIdError, InvalidProjectIdFormatError) as e:
            logger.warning(f"Invalid projectid file at {projectid_path}: {e}, skipping")
            continue
        except NestedProjectError as e:
            # Check if nested project is in subdirectory (child) or parent
            child_project = e.child_project
            if child_project is None:
                logger.warning("NestedProjectError with no child_project, skipping")
                continue
            nested_path = Path(child_project)
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


def discover_project_candidates_in_directory(watch_dir: Path) -> List[ProjectRoot]:
    """
    Cheap immediate-child project discovery: no recursive/nested validation.

    User decision (2026-07-23): a legitimate project is defined solely as
    "immediate child of a watched directory with a correct ``projectid``
    file" -- nothing else is checked at listing time. Unlike
    :func:`discover_projects_in_directory`, this performs **no** ``os.walk``
    anywhere (no :func:`validate_no_nested_projects` call), which makes it
    safe to run over every candidate on every ``list_projects`` call
    regardless of catalog size.

    Membership test = ``projectid`` file presence at ``watch_dir/<subdir>/``.
    A subdirectory without a ``projectid`` file is not a project and is
    skipped silently (no log at all -- a foreign directory in a watched
    catalog is an expected, normal shape, not worth event volume). A
    ``projectid`` file that fails to parse (invalid JSON / missing ``id`` /
    bad UUID4) skips its directory with a debug-level log only; one
    malformed or foreign directory never fails the whole listing.

    The historical "is this immediate child nested inside another immediate
    child" guard from :func:`discover_projects_in_directory` is not
    reproduced here: two immediate children of the same ``watch_dir`` are
    always siblings (each exactly one path segment below ``watch_dir``), so
    neither can ever be a subpath of the other -- that check can never fire
    for this candidate set.

    Duplicate ``project_id`` across immediate children of the SAME
    ``watch_dir`` is still validated (an in-memory hash-map check, not a
    walk) and raises :class:`DuplicateProjectIdError`, matching
    :func:`discover_projects_in_directory`'s existing per-watch-dir dedupe
    scope.

    Args:
        watch_dir: Watched directory to scan.

    Returns:
        ``ProjectRoot`` list (with ``deleted``/``processing_paused``
        populated from the single ``load_project_info`` read each), stably
        sorted by lowercased directory name with ``project_id`` as tie-break.

    Raises:
        DuplicateProjectIdError: If duplicate project_id detected.
    """
    watch_dir = Path(watch_dir).resolve()
    if not watch_dir.exists() or not watch_dir.is_dir():
        logger.warning(
            f"Watch directory does not exist or is not a directory: {watch_dir}"
        )
        return []

    try:
        entries = list(watch_dir.iterdir())
    except OSError as e:
        logger.error(f"Error scanning watch directory {watch_dir}: {e}")
        return []

    from .project_resolution import load_project_info

    candidates: List[ProjectRoot] = []
    for item in entries:
        try:
            if not item.is_dir():
                continue
        except OSError:
            continue
        projectid_path = item / "projectid"
        try:
            if not (projectid_path.exists() and projectid_path.is_file()):
                continue
        except OSError:
            continue
        try:
            info = load_project_info(item)
        except (ProjectIdError, InvalidProjectIdFormatError) as e:
            logger.debug(
                f"Skipping unreadable/invalid projectid at {projectid_path}: {e}"
            )
            continue
        candidates.append(
            ProjectRoot(
                root_path=info.root_path,
                project_id=info.project_id,
                description=info.description,
                watch_dir=watch_dir,
                deleted=info.deleted,
                processing_paused=info.processing_paused,
            )
        )

    candidates.sort(key=lambda p: (p.root_path.name.lower(), p.project_id))

    # Validate no duplicate project_ids within this watch_dir
    validate_no_duplicate_project_ids(candidates)

    return candidates
