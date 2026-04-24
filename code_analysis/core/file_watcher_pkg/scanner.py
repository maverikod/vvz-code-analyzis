"""
Directory scanner for file watcher worker.

Scans configured directories for code files and discovers projects.

Directory pruning (``should_skip_dir``) avoids descending into nested ``test_data``
mirrors, ``data/trash``, caches, and noisy venv subtrees while still allowing
``.venv``/``venv`` → ``lib``/``python*``/``site-packages`` for allowlisted indexing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import fnmatch
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..settings_manager import get_settings

logger = logging.getLogger(__name__)

# Get settings from SettingsManager
settings = get_settings()

# File extensions to process (from settings)
CODE_FILE_EXTENSIONS = set(settings.get("code_file_extensions"))

# Default patterns to ignore (from settings)
DEFAULT_IGNORE_PATTERNS = set(settings.get("default_ignore_patterns"))

# Basenames to prune at traversal time (filesystem-only; no DB).
_SKIP_DIR_BASENAMES = frozenset(
    {
        "__pycache__",
        ".git",
        "node_modules",
        "build",
        "dist",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "eggs",
        ".eggs",
        "wheels",
        ".tox",
        "htmlcov",
        ".cache",
        "ENV",
        "env",
        "env.bak",
        "venv.bak",
    }
)


def _path_has_adjacent_parts(parts: tuple[str, ...], a: str, b: str) -> bool:
    for i in range(len(parts) - 1):
        if parts[i] == a and parts[i + 1] == b:
            return True
    return False


def _nested_test_data_mirror(dir_path: Path, walk_root: Path) -> bool:
    """
    True if this directory is a nested ``test_data`` copy under ``walk_root``.

    Allows a single top-level ``<walk_root>/test_data`` segment (watch root layout
    or a project folder named ``test_data``); prunes deeper ``.../test_data/...``.
    """
    if dir_path.name != "test_data":
        return False
    try:
        rel = dir_path.resolve().relative_to(walk_root.resolve())
    except (OSError, ValueError):
        return True
    return len(rel.parts) >= 2


def should_skip_dir(dir_path: Path, *, walk_root: Path) -> bool:
    """
    Return True if the file watcher must not descend into this directory.

    Prunes nested test mirrors, application trash/trees, caches, and venv noise
    (``bin``/``include``/… under ``.venv``) while keeping the ``site-packages`` chain.

    Args:
        dir_path: Candidate subdirectory (typically ``parent / name`` from ``os.walk``).
        walk_root: Root of the current ``os.walk`` (scan root or project root).

    Returns:
        True to skip traversal into ``dir_path``.
    """
    try:
        resolved = dir_path.resolve()
        wr = walk_root.resolve()
    except OSError:
        resolved = dir_path
        wr = walk_root
    if resolved == wr:
        return False
    parts = resolved.parts
    if _nested_test_data_mirror(dir_path, walk_root):
        return True
    if _path_has_adjacent_parts(parts, "data", "trash"):
        return True
    if _path_has_adjacent_parts(parts, "data", "versions"):
        return True
    name = resolved.name
    if name in _SKIP_DIR_BASENAMES:
        return True
    parent = resolved.parent
    pn, cn = parent.name, name
    if pn in (".venv", "venv") and cn in (
        "bin",
        "include",
        "share",
        "etc",
        "Scripts",
    ):
        return True
    gpp = parent.parent
    if gpp.name in (".venv", "venv") and pn == "lib" and not cn.startswith("python"):
        return True
    if (
        pn.startswith("python")
        and gpp.name == "lib"
        and gpp.parent.name in (".venv", "venv")
        and cn != "site-packages"
    ):
        return True
    return False


def is_traversable_venv_root(path: Path) -> bool:
    """Allow descending into project-local ``.venv`` / ``venv`` roots."""
    return path.is_dir() and path.name in (".venv", "venv")


def should_ignore_path(
    path: Path,
    ignore_patterns: Optional[List[str]] = None,
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
) -> bool:
    """
    Check if path should be ignored.

    Args:
        path: Path to check
        ignore_patterns: Additional ignore patterns from config (optional)
        allowed_venv_py_files: Optional set of resolved paths under project ``.venv``/``venv``
            ``site-packages`` that are allowlisted for indexing (see config). If a file
            path resolves to a member, it is not ignored.
        ignore_exception_files: Optional set of resolved ``.py`` paths that must not be ignored
            (``code_analysis.ignore_exceptions``), evaluated before default ignores.

    Returns:
        True if path should be ignored, False otherwise
    """
    if ignore_exception_files and path.is_file():
        try:
            if path.resolve() in ignore_exception_files:
                return False
        except OSError:
            pass

    if allowed_venv_py_files and path.is_file():
        try:
            if path.resolve() in allowed_venv_py_files:
                return False
        except OSError:
            pass

    # Combine default and config patterns
    all_patterns = set(DEFAULT_IGNORE_PATTERNS)
    if ignore_patterns:
        all_patterns.update(ignore_patterns)

    # Convert path to string for pattern matching
    path_str = str(path)
    rel_path_str = None
    if path.is_absolute():
        # Try to get relative path for better matching
        try:
            rel_path_str = str(path.relative_to(path.anchor))
        except (ValueError, AttributeError):
            pass

    # Check each part of the path
    for part in path.parts:
        # Direct name match
        if part in all_patterns:
            return True

        # Special handling for "data" and "versions" directories
        if part == "data":
            # Check if next part is "versions" or if path contains "data/versions"
            try:
                part_idx = path.parts.index(part)
                if (
                    part_idx + 1 < len(path.parts)
                    and path.parts[part_idx + 1] == "versions"
                ):
                    return True
            except (ValueError, IndexError):
                pass

    # Pattern matching for full path and subpaths
    for pattern in all_patterns:
        # Check if pattern matches full path
        if fnmatch.fnmatch(path_str, pattern):
            return True
        if rel_path_str and fnmatch.fnmatch(rel_path_str, pattern):
            return True

        # Check if pattern matches any part of the path
        if "**" in pattern or "/" in pattern:
            # Glob pattern with ** or path separator
            for i in range(len(path.parts)):
                subpath = "/".join(path.parts[i:])
                if fnmatch.fnmatch(subpath, pattern):
                    return True
                # Also check with leading slash
                if fnmatch.fnmatch("/" + subpath, pattern):
                    return True

        # Simple pattern matching for each part
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True

    # Check for hidden directories (except current/parent)
    for part in path.parts:
        if part.startswith(".") and part != "." and part != "..":
            if path.is_dir():
                return True

    # Check file extension
    if path.is_file():
        return path.suffix not in CODE_FILE_EXTENSIONS

    return False


def scan_directory(
    root_dir: Path,
    watch_dirs: List[Path],
    ignore_patterns: Optional[List[str]] = None,
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
) -> Dict[str, Dict]:
    """
    Scan directory recursively for code files and discover projects.

    Implements project discovery: for each file, finds the project root as the
    directory ``watch_dir/<one_segment>/`` that contains a valid ``projectid``
    (only immediate children of each watch_dir; see ``project_discovery.find_project_root``).

    Args:
        root_dir: Root directory to scan
        watch_dirs: List of watched directories for project discovery (REQUIRED)
        ignore_patterns: Glob patterns to ignore
        allowed_venv_py_files: Optional set of resolved ``.py`` paths under venv
            ``site-packages`` that are allowlisted for discovery (see config).
        ignore_exception_files: Optional set of resolved paths matching
            ``code_analysis.ignore_exceptions`` (force include).

    Returns:
        Dictionary mapping absolute file paths to file info:
        {
            "/absolute/path/to/file.py": {
                "path": Path("/absolute/path/to/file.py"),
                "mtime": 1234567890.0,
                "size": 1024,
                "project_root": Path("/project/root"),
                "project_id": "uuid-here",
            }
        }

        Files without a project (no projectid found) are skipped with a warning.
    """
    from ..path_normalization import normalize_file_path
    from ..exceptions import NestedProjectError, ProjectNotFoundError
    from typing import Any

    files: Dict[str, Dict] = {}

    # Resolve watch_dirs to absolute paths
    watch_dirs_resolved = [Path(wd).resolve() for wd in watch_dirs]

    try:
        walk_root = root_dir.resolve()
    except OSError:
        walk_root = root_dir

    try:
        for dirpath, dirnames, filenames in os.walk(
            walk_root, topdown=True, followlinks=False
        ):
            dir_path = Path(dirpath)
            # Prune before visiting children: traversal exclusions + ignore patterns.
            pruned: List[str] = []
            for d in sorted(dirnames):
                child_dir = dir_path / d
                if should_skip_dir(child_dir, walk_root=walk_root):
                    continue
                if should_ignore_path(
                    child_dir,
                    ignore_patterns,
                    allowed_venv_py_files=allowed_venv_py_files,
                    ignore_exception_files=ignore_exception_files,
                ) and not is_traversable_venv_root(child_dir):
                    continue
                pruned.append(d)
            dirnames[:] = pruned

            for name in filenames:
                item = dir_path / name
                if should_ignore_path(
                    item,
                    ignore_patterns,
                    allowed_venv_py_files=allowed_venv_py_files,
                    ignore_exception_files=ignore_exception_files,
                ):
                    continue
                if not item.is_file():
                    continue
                try:
                    stat = item.stat()
                    try:
                        normalized = normalize_file_path(
                            item, watch_dirs=watch_dirs_resolved
                        )
                        path_key = normalized.absolute_path

                        file_info: Dict[str, Any] = {
                            "path": Path(normalized.absolute_path),
                            "mtime": stat.st_mtime,
                            "size": stat.st_size,
                            "project_root": normalized.project_root,
                            "project_id": normalized.project_id,
                        }
                        files[path_key] = file_info
                    except (ProjectNotFoundError, NestedProjectError) as e:
                        logger.warning(
                            f"No project found for file {item}: {e}, skipping"
                        )
                        continue
                    except Exception as e:
                        logger.debug(f"Error normalizing path for {item}: {e}")
                        continue
                except OSError as e:
                    logger.debug(f"Error accessing file {item}: {e}")
                    continue

    except OSError as e:
        logger.error(f"Error scanning directory {root_dir}: {e}")

    return files


def find_missing_files(
    scanned_files: Dict[str, Dict], db_files: List[Dict]
) -> Set[str]:
    """
    Find files that exist in database but not on disk.

    Args:
        scanned_files: Files found on disk (from scan_directory)
        db_files: Files in database

    Returns:
        Set of file paths that are missing on disk
    """
    missing = set()
    for db_file in db_files:
        file_path = db_file.get("path")
        if file_path and file_path not in scanned_files:
            missing.add(file_path)
    return missing
