"""
Directory scanner for file watcher worker.

Scans configured directories for code files and discovers projects.

Traversal pruning (``should_skip_dir``) runs **before** ``should_ignore_path`` on
directory children: excluded trees (``test_data``, ``data/trash``, etc.) are never
entered. ``should_ignore_path`` remains file-level and secondary for dirs.
``.venv``/``venv`` roots stay traversable; noisy subtrees under them are pruned for
allowlisted ``site-packages`` indexing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import fnmatch
import logging
import os
from pathlib import Path
from typing import AbstractSet, Dict, List, Optional, Sequence, Set

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


def _path_pattern_candidates(path: Path, project_root: Optional[Path]) -> Set[str]:
    """POSIX-style absolute/relative candidates for glob matching."""
    out: Set[str] = set()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    abs_posix = resolved.as_posix()
    out.add(abs_posix)
    out.add(abs_posix.lstrip("/"))
    out.add("/" + abs_posix.lstrip("/"))
    if project_root is not None:
        try:
            root_resolved = project_root.resolve()
        except OSError:
            root_resolved = project_root
        try:
            rel = resolved.relative_to(root_resolved).as_posix()
            out.add(rel)
            out.add("/" + rel.lstrip("/"))
        except ValueError:
            pass
    return out


def _matches_any_glob(
    path: Path, patterns: Optional[List[str]], *, project_root: Optional[Path]
) -> bool:
    """Return True when any pattern matches path candidates/subpaths."""
    if not patterns:
        return False
    candidates = _path_pattern_candidates(path, project_root)
    for pattern in patterns:
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern):
                return True
            parts = [p for p in candidate.split("/") if p]
            for i in range(len(parts)):
                sub = "/".join(parts[i:])
                if fnmatch.fnmatch(sub, pattern) or fnmatch.fnmatch("/" + sub, pattern):
                    return True
    return False


def _pattern_parts_without_globs(pattern: str) -> tuple[str, ...]:
    """Literal POSIX path segments from a glob pattern."""
    parts: list[str] = []
    for part in pattern.replace("\\", "/").split("/"):
        token = part.strip()
        if not token or token in (".", "**"):
            continue
        if any(ch in token for ch in "*?[]"):
            continue
        parts.append(token)
    return tuple(parts)


def may_contain_ignore_exception(
    dir_path: Path, project_root: Path, exception_patterns: Sequence[str]
) -> bool:
    """
    Conservative check for whether an ignored directory may contain exceptions.

    The function keeps traversal open only when the directory path is compatible
    with at least one exception glob pattern.
    """
    if not exception_patterns:
        return False
    try:
        dir_resolved = dir_path.resolve()
    except OSError:
        dir_resolved = dir_path
    try:
        root_resolved = project_root.resolve()
    except OSError:
        root_resolved = project_root
    try:
        dir_rel = dir_resolved.relative_to(root_resolved).as_posix().strip("/")
    except ValueError:
        return True
    if not dir_rel:
        return True
    dir_parts = tuple(p for p in dir_rel.split("/") if p)
    for raw_pattern in exception_patterns:
        pattern = str(raw_pattern).strip()
        if not pattern:
            continue
        if fnmatch.fnmatch(dir_rel, pattern) or fnmatch.fnmatch("/" + dir_rel, pattern):
            return True
        literal_parts = _pattern_parts_without_globs(pattern)
        if not literal_parts:
            return True
        max_start = len(literal_parts) - len(dir_parts)
        if max_start < 0:
            continue
        for idx in range(max_start + 1):
            if literal_parts[idx : idx + len(dir_parts)] == dir_parts:
                return True
    return False


def _path_has_adjacent_parts(parts: tuple[str, ...], a: str, b: str) -> bool:
    for i in range(len(parts) - 1):
        if parts[i] == a and parts[i + 1] == b:
            return True
    return False


def _under_data_trash(parts: tuple[str, ...], posix_path: str) -> bool:
    """True if path is under an application ``data/trash`` tree (name + full path)."""
    if _path_has_adjacent_parts(parts, "data", "trash"):
        return True
    norm = posix_path if posix_path.endswith("/") else posix_path + "/"
    return "/data/trash/" in norm


def _best_project_root_for_path(
    path: Path,
    immediate_project_roots: Optional[AbstractSet[Path]],
    fallback_root: Path,
) -> Path:
    """
    Return the deepest known project root containing ``path``.

    Falls back to ``fallback_root`` when project roots are not available or no
    candidate contains the path.
    """
    if not immediate_project_roots:
        return fallback_root
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    best: Optional[Path] = None
    best_depth = -1
    for candidate in immediate_project_roots:
        try:
            resolved.relative_to(candidate)
        except ValueError:
            continue
        depth = len(candidate.parts)
        if depth > best_depth:
            best = candidate
            best_depth = depth
    return best if best is not None else fallback_root


def should_skip_dir(
    dir_path: Path,
    walk_root: Path | None = None,
    *,
    immediate_project_roots: Optional[AbstractSet[Path]] = None,
) -> bool:
    """
    Return True if the file watcher must not descend into this directory.

    Filesystem-only traversal control (not ``should_ignore_path``). Skips any
    directory named ``test_data`` (except resolved roots listed in
    ``immediate_project_roots``), paths under ``data/trash`` (by path segments and
    ``/data/trash/`` in the full path), ``data/versions``, common build/cache dirs,
    and non-indexable subtrees under ``.venv``/``venv`` while keeping the
    ``site-packages`` chain for optional allowlists.

    Args:
        dir_path: Candidate subdirectory (typically ``parent / name`` from ``os.walk``).
        walk_root: Root of the current ``os.walk`` (``scan_directory`` ``root_dir``).
            When omitted, only path-shape rules apply (no ``dir_path == walk_root`` exemption).
        immediate_project_roots: Resolved project roots that may not be pruned solely
            for being named ``test_data``.

    Returns:
        True to skip traversal into ``dir_path``.
    """
    try:
        resolved = dir_path.resolve()
    except OSError:
        resolved = dir_path
    if walk_root is not None:
        try:
            wr = walk_root.resolve()
        except OSError:
            wr = walk_root
        if resolved == wr:
            return False
    parts = resolved.parts
    posix_path = resolved.as_posix()
    if _under_data_trash(parts, posix_path):
        return True
    if resolved.name == "test_data":
        if immediate_project_roots and resolved in immediate_project_roots:
            return False
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


def should_prune_ignored_dir(
    dir_path: Path,
    ignore_patterns: Optional[List[str]] = None,
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    ignore_exception_patterns: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """
    Return True when an ignored directory can be safely pruned.

    If any ignore-exception file is located under ``dir_path``, we must keep
    traversing this subtree so exception paths can be discovered.
    """
    if not should_ignore_path(
        dir_path,
        ignore_patterns,
        allowed_venv_py_files=allowed_venv_py_files,
        ignore_exception_files=ignore_exception_files,
        ignore_exception_patterns=ignore_exception_patterns,
        project_root=project_root,
    ):
        return False
    if is_traversable_venv_root(dir_path):
        return False
    if ignore_exception_patterns:
        root = project_root
        if root is None:
            # Conservative fallback: when we cannot evaluate exception globs
            # against a reliable root, do not prune to avoid dropping exception files.
            return False
        if may_contain_ignore_exception(dir_path, root, ignore_exception_patterns):
            return False
        return True
    if not ignore_exception_files:
        return True
    try:
        dir_resolved = dir_path.resolve()
    except OSError:
        dir_resolved = dir_path
    for exc_file in ignore_exception_files:
        try:
            Path(exc_file).resolve().relative_to(dir_resolved)
            return False
        except (ValueError, OSError):
            continue
    return True


def should_ignore_path(
    path: Path,
    ignore_patterns: Optional[List[str]] = None,
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    ignore_exception_patterns: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
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
    if _matches_any_glob(path, ignore_exception_patterns, project_root=project_root):
        return False

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
    candidates = _path_pattern_candidates(path, project_root)

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
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern):
                return True
            if "**" in pattern or "/" in pattern:
                parts = [p for p in candidate.split("/") if p]
                for i in range(len(parts)):
                    subpath = "/".join(parts[i:])
                    if fnmatch.fnmatch(subpath, pattern):
                        return True
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
    ignore_exception_patterns: Optional[List[str]] = None,
    immediate_project_roots: Optional[AbstractSet[Path]] = None,
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
        immediate_project_roots: Resolved ``watch_dir/<project>/`` roots from
            discovery; keeps a project folder named ``test_data`` traversable.

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

    resolved_project_roots: Optional[AbstractSet[Path]] = None
    if immediate_project_roots:
        resolved_project_roots = set()
        for pr in immediate_project_roots:
            try:
                resolved_project_roots.add(Path(pr).resolve())
            except OSError:
                resolved_project_roots.add(Path(pr))

    try:
        for dirpath, dirnames, filenames in os.walk(
            walk_root, topdown=True, followlinks=False
        ):
            dir_path = Path(dirpath)
            current_project_root = _best_project_root_for_path(
                dir_path, resolved_project_roots, walk_root
            )
            # Pre-traversal: prune excluded directory trees before any ignore-pattern logic.
            dirnames[:] = [
                d
                for d in sorted(dirnames)
                if not should_skip_dir(
                    dir_path / d,
                    walk_root,
                    immediate_project_roots=resolved_project_roots,
                )
            ]
            # Secondary: pattern-based directory filtering (file-level rules); keep venv roots.
            dirnames[:] = [
                d
                for d in sorted(dirnames)
                if not should_prune_ignored_dir(
                    dir_path / d,
                    ignore_patterns,
                    allowed_venv_py_files=allowed_venv_py_files,
                    ignore_exception_files=ignore_exception_files,
                    ignore_exception_patterns=ignore_exception_patterns,
                    project_root=current_project_root,
                )
            ]

            for name in filenames:
                item = dir_path / name
                file_project_root = _best_project_root_for_path(
                    item, resolved_project_roots, current_project_root
                )
                if should_ignore_path(
                    item,
                    ignore_patterns,
                    allowed_venv_py_files=allowed_venv_py_files,
                    ignore_exception_files=ignore_exception_files,
                    ignore_exception_patterns=ignore_exception_patterns,
                    project_root=file_project_root,
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
