"""
Directory scanner for file watcher worker.

Scans configured directories for code files and discovers projects.

Traversal pruning (``should_skip_dir``) runs **before** ``should_ignore_path`` on
directory children: excluded trees (``test_data``, ``data/trash``, ``.venv``,
``venv``, etc.) are never entered. Allowlisted virtualenv ``.py`` files are merged
after the walk via explicit RECORD paths (no full ``site-packages`` traversal).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import fnmatch

import logging

import os

from pathlib import Path

from typing import AbstractSet, Any, Dict, List, Optional, Sequence, Set, Union


from ..project_ignore_policy import (
    DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES,
    filter_ignore_exception_py_paths_for_watcher,
    path_is_under_project_local_venv,
)

from ..docs_indexing_defaults import DOCS_INDEX_FILE_SUFFIXES
from ..docs_indexing_eligibility import is_docs_markdown_eligible
from ..settings_manager import get_settings


logger = logging.getLogger(__name__)


# Get settings from SettingsManager
settings = get_settings()


# File extensions to process (from settings)
CODE_FILE_EXTENSIONS = set(settings.get("code_file_extensions"))


# Default patterns to ignore (from settings)
DEFAULT_IGNORE_PATTERNS = set(settings.get("default_ignore_patterns"))


# Basenames to prune at traversal time (filesystem-only; no DB).
_SKIP_DIR_BASENAMES = frozenset(DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES)


def _relative_posix_under_project_root(
    path: Path, project_root: Optional[Path]
) -> Optional[str]:
    """Project-relative POSIX path for docs eligibility; None if not under root."""
    if project_root is None:
        return None
    try:
        pres = path.resolve()
        rres = project_root.resolve()
        return pres.relative_to(rres).as_posix()
    except (OSError, ValueError):
        return None


def _path_pattern_candidates(path: Path, project_root: Optional[Path]) -> Set[str]:
    """POSIX-style absolute/relative candidates for glob matching.

    Args:
        path: Filesystem path to generate candidates for.
        project_root: Optional project root used to compute relative candidates.

    Returns:
        Set of candidate strings for glob matching.
    """
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
    """Return True when any pattern matches path candidates/subpaths.

    Args:
        path: Filesystem path to match against patterns.
        patterns: List of glob patterns to test.
        project_root: Optional root for relative path candidate generation.

    Returns:
        True if any pattern matches any candidate derived from path.
    """
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
    """Literal POSIX path segments from a glob pattern.

    Args:
        pattern: Glob pattern string to extract literal segments from.

    Returns:
        Tuple of literal path segment strings without any glob characters.
    """
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

    Args:
        dir_path: Directory path to test.
        project_root: Project root used to compute relative path.
        exception_patterns: Glob patterns for ignore exceptions.

    Returns:
        True if the directory may contain files matching an exception pattern.
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
    """Return True if ``a`` is immediately followed by ``b`` in ``parts``.

    Args:
        parts: Tuple of path segments to search.
        a: First segment to look for.
        b: Second segment that must follow ``a``.

    Returns:
        True if ``a`` is directly followed by ``b`` anywhere in parts.
    """
    for i in range(len(parts) - 1):
        if parts[i] == a and parts[i + 1] == b:
            return True
    return False


def _under_data_trash(parts: tuple[str, ...], posix_path: str) -> bool:
    """True if path is under an application ``data/trash`` tree (name + full path).

    Args:
        parts: Tuple of resolved path segments.
        posix_path: POSIX string representation of the resolved path.

    Returns:
        True if the path is located under a ``data/trash`` directory.
    """
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

    Args:
        path: Filesystem path to find the best project root for.
        immediate_project_roots: Set of resolved project root paths.
        fallback_root: Root to return when no matching project root is found.

    Returns:
        The deepest project root that contains path, or fallback_root.
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
    soft_deleted_project_roots: Optional[AbstractSet[Path]] = None,
) -> bool:
    """
    Return True if the file watcher must not descend into this directory.

    Filesystem-only traversal control (not ``should_ignore_path``). Skips any
    directory named ``test_data`` (except resolved roots listed in
    ``immediate_project_roots``), paths under ``data/trash`` (by path segments and
    ``/data/trash/`` in the full path), ``data/versions``, virtualenvs, VCS, caches,
    and other names in :data:`DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES`.

    Args:
        dir_path: Candidate subdirectory (typically ``parent / name`` from ``os.walk``).
        walk_root: Root of the current ``os.walk`` (``scan_directory`` ``root_dir``).
            When omitted, only path-shape rules apply (no ``dir_path == walk_root`` exemption).
        immediate_project_roots: Resolved project roots that may not be pruned solely
            for being named ``test_data``.
        soft_deleted_project_roots: Project roots marked ``projects.deleted`` in the DB;
            the watcher must not descend into these trees (no re-index / no auto-register).

    Returns:
        True to skip traversal into ``dir_path``.
    """
    # Fast basename check -- no resolve() syscall needed.
    name = dir_path.name
    if name in _SKIP_DIR_BASENAMES:
        return True
    # resolve() is required for all remaining checks.
    try:
        resolved = dir_path.resolve()
    except OSError:
        resolved = dir_path
    if soft_deleted_project_roots:
        for ex in soft_deleted_project_roots:
            try:
                exr = ex.resolve()
            except OSError:
                exr = ex
            try:
                resolved.relative_to(exr)
                return True
            except ValueError:
                continue
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
    return False


def should_prune_ignored_dir(
    dir_path: Path,
    ignore_patterns: Optional[List[str]] = None,
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    ignore_exception_patterns: Optional[List[str]] = None,
    project_root: Optional[Path] = None,
    docs_indexing: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Return True when an ignored directory can be safely pruned.

    If any ignore-exception file is located under ``dir_path``, we must keep
    traversing this subtree so exception paths can be discovered.

    Args:
        dir_path: Directory path to test for pruning.
        ignore_patterns: List of glob patterns for ignored paths.
        allowed_venv_py_files: Set of explicitly allowed venv Python files.
        ignore_exception_files: Set of files that are exceptions to ignore rules.
        ignore_exception_patterns: Glob patterns for ignore exceptions.
        project_root: Root of the project for relative path computation.

    Returns:
        True if the directory should be pruned from traversal.
    """
    if not should_ignore_path(
        dir_path,
        ignore_patterns,
        allowed_venv_py_files=allowed_venv_py_files,
        ignore_exception_files=ignore_exception_files,
        ignore_exception_patterns=ignore_exception_patterns,
        project_root=project_root,
        docs_indexing=docs_indexing,
    ):
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
    docs_indexing: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Check if path should be ignored.

    Args:
        path: Path to check
        ignore_patterns: Additional ignore patterns from config (optional)
        allowed_venv_py_files: Optional set of resolved paths under project ``.venv``/``venv``
            ``site-packages`` that are allowlisted for indexing (see config). If a file
            path resolves to a member, it is not ignored.
        ignore_exception_files: Optional set of resolved paths from
            ``code_analysis.ignore_exceptions``. Paths under ``.venv``/``venv`` are
            not force-included unless they appear in ``allowed_venv_py_files``.
        docs_indexing: Enabled-docs snapshot from server config; ``.md`` / ``.json`` /
            ``.yaml`` / ``.yml`` files may be admitted via eligibility (otherwise suffix rules apply).

    Returns:
        True if path should be ignored, False otherwise
    """
    if ignore_exception_files and path.is_file():
        try:
            res = path.resolve()
        except OSError:
            res = path
        if res in ignore_exception_files:
            if project_root is not None and path_is_under_project_local_venv(
                res, project_root
            ):
                allowed = allowed_venv_py_files or set()
                if res not in allowed:
                    pass
                else:
                    return False
            else:
                return False
    if ignore_exception_patterns and _matches_any_glob(
        path, ignore_exception_patterns, project_root=project_root
    ):
        if project_root is not None and path_is_under_project_local_venv(
            path, project_root
        ):
            if allowed_venv_py_files and path.is_file():
                try:
                    if path.resolve() in allowed_venv_py_files:
                        return False
                except OSError:
                    pass
            return True
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

    # Check file extension (and optional docs indexing gate: .md / .json / .yaml / .yml)
    if path.is_file():
        suf = path.suffix.lower()
        if suf in DOCS_INDEX_FILE_SUFFIXES and docs_indexing is not None:
            rel = _relative_posix_under_project_root(path, project_root)
            if rel is None:
                logger.debug(
                    "[DOCS_INDEX_WATCHER] skip docs path=%s reason=no_project_relative",
                    path,
                )
                return True
            verdict = is_docs_markdown_eligible(
                docs_indexing=docs_indexing,
                relative_path=rel,
                file_exists=path.exists(),
                is_deleted=False,
            )
            if verdict.eligible:
                return False
            logger.debug(
                "[DOCS_INDEX_WATCHER] skip docs path=%s reasons=%s",
                path,
                verdict.reason_codes,
            )
            return True
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
    soft_deleted_project_roots: Optional[AbstractSet[Path]] = None,
    docs_indexing: Optional[Dict[str, Any]] = None,
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
        soft_deleted_project_roots: Subtrees excluded from traversal (DB
            ``projects.deleted`` for that root).
        docs_indexing: Optional enabled-docs snapshot from server config for ``.md`` / ``.json`` / ``.yaml`` / ``.yml``.

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

        Explicit merge paths (allowlisted venv + ``ignore_exception_files``) never
        walk ``.venv``; ``ignore_exception_files`` under a project venv are dropped
        on merge unless ``allowed_venv_py_files`` contains them and
        ``immediate_project_roots`` is provided (same as
        :func:`~code_analysis.core.project_ignore_policy.filter_ignore_exception_py_paths_for_watcher`).
    """
    from ..exceptions import NestedProjectError, ProjectNotFoundError
    from ..path_normalization import normalize_file_path

    files: Dict[str, Dict[str, Any]] = {}

    # Resolve watch_dirs to absolute paths; annotated as List[Union[str, Path]]
    # to satisfy normalize_file_path signature.
    watch_dirs_resolved: List[Union[str, Path]] = [
        Path(wd).resolve() for wd in watch_dirs
    ]

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

    resolved_soft_deleted: Optional[AbstractSet[Path]] = None
    if soft_deleted_project_roots:
        resolved_soft_deleted = set()
        for pr in soft_deleted_project_roots:
            try:
                resolved_soft_deleted.add(Path(pr).resolve())
            except OSError:
                resolved_soft_deleted.add(Path(pr))

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
                    soft_deleted_project_roots=resolved_soft_deleted,
                )
            ]
            # Secondary: pattern-based directory pruning for ignored directory shapes.
            dirnames[:] = [
                d
                for d in dirnames
                if not should_prune_ignored_dir(
                    dir_path / d,
                    ignore_patterns,
                    allowed_venv_py_files=allowed_venv_py_files,
                    ignore_exception_files=ignore_exception_files,
                    ignore_exception_patterns=ignore_exception_patterns,
                    project_root=current_project_root,
                    docs_indexing=docs_indexing,
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
                    docs_indexing=docs_indexing,
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

    merge_paths: Set[Path] = set()
    if allowed_venv_py_files:
        merge_paths.update(allowed_venv_py_files)
    if ignore_exception_files:
        exc_merge: Set[Path] = set(ignore_exception_files)
        if resolved_project_roots:
            exc_merge = filter_ignore_exception_py_paths_for_watcher(
                exc_merge,
                resolved_project_roots,
                allowed_venv_py_files,
            )
        merge_paths.update(exc_merge)
    _merge_explicit_watcher_file_paths(
        files,
        watch_dirs_resolved,
        merge_paths,
        resolved_soft_deleted,
    )

    return files


def _merge_explicit_watcher_file_paths(
    files: Dict[str, Dict[str, Any]],
    watch_dirs_resolved: List[Union[str, Path]],
    explicit_absolute_paths: AbstractSet[Path],
    resolved_soft_deleted: Optional[AbstractSet[Path]],
) -> None:
    """Add allowlisted venv / filtered ignore-exception files without walking ``.venv``.

    Args:
        files: Dictionary of already-scanned files to merge into.
        watch_dirs_resolved: List of resolved watch directory paths.
        explicit_absolute_paths: Set of absolute paths to merge explicitly.
        resolved_soft_deleted: Set of soft-deleted project roots to skip.

    Returns:
        None
    """
    from ..exceptions import NestedProjectError, ProjectNotFoundError
    from ..path_normalization import normalize_file_path

    if not explicit_absolute_paths:
        return
    for item in explicit_absolute_paths:
        try:
            if not item.is_file():
                continue
        except OSError:
            continue
        if resolved_soft_deleted:
            try:
                ir = item.resolve()
            except OSError:
                ir = item
            skip_merged = False
            for ex in resolved_soft_deleted:
                try:
                    ir.relative_to(ex)
                    skip_merged = True
                    break
                except ValueError:
                    continue
            if skip_merged:
                continue
        try:
            stat = item.stat()
            normalized = normalize_file_path(item, watch_dirs=watch_dirs_resolved)
            path_key = normalized.absolute_path
            files[path_key] = {
                "path": Path(normalized.absolute_path),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "project_root": normalized.project_root,
                "project_id": normalized.project_id,
            }
        except (ProjectNotFoundError, NestedProjectError) as e:
            logger.warning("No project found for merged file %s: %s", item, e)
        except Exception as e:
            logger.debug("Error normalizing merged path %s: %s", item, e)


def find_missing_files(
    scanned_files: Dict[str, Dict],
    db_files: List[Dict],
    project_root: Path,
) -> Set[str]:
    """
    Find files that exist in database but not on disk.

    Args:
        scanned_files: Files found on disk for this project, keyed by **project-relative**
            POSIX path (same keys as :func:`compute_delta` uses per project).
        db_files: Files in database (``path`` may be project-relative or legacy absolute)
        project_root: Project root for resolving DB rows

    Returns:
        Set of **project-relative** POSIX paths that are missing on disk
    """
    from ..path_normalization import normalize_path_simple
    from ..file_identity import absolute_path_for_indexed_file, relative_path_for_project

    missing: set[str] = set()
    root = project_root.resolve()
    for db_file in db_files:
        abs_key = normalize_path_simple(absolute_path_for_indexed_file(root, db_file))
        try:
            rel_key = relative_path_for_project(abs_key, root)
        except ValueError:
            continue
        if rel_key not in scanned_files:
            missing.add(rel_key)
    return missing
