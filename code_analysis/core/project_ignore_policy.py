"""
Shared ignore rules for watcher traversal, indexing alignment, and project file listing.

Production defaults skip virtualenv trees, VCS, caches, build artifacts, and common
generated files. Paths under ``.venv`` / ``venv`` are not force-included via
``ignore_exceptions`` glob expansion alone; only allowlisted RECORD-resolved
site-packages paths (and optional diagnostic listing flags) may surface them.

**Callers (by symbol)** — config expansion stays in workers / ``venv_path_policy``:

- ``path_is_under_project_local_venv``: ``scanner`` (ignore / merge), ``venv_path_policy``.
- ``is_ignored_project_relative_path`` / ``filter_paths_for_default_project_listing`` /
  ``LISTING_CACHE_DIRECTORY_SEGMENTS``:
  ``commands/ast/list_files`` (default listing); chunking / indexing should align via
  the same relative-path rules where applicable (listing-only ``show_hidden``).
- ``sql_and_absolute_path_eligible_for_default_status_aggregates``:
  ``commands/worker_status_mcp_commands/get_database_status_build`` (SQL fragments).
- ``filter_ignore_exception_py_paths_for_watcher``: ``multi_project_worker_scan``,
  ``multi_project_worker``, ``file_watcher_pkg/base``, ``venv_path_policy``; defensive
  merge filtering in ``scanner.scan_directory`` when ``immediate_project_roots`` is set.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import AbstractSet, Collection, FrozenSet, Optional

# Well-known directory / path segment names (single source for watcher + listing).
DATA_DIR_BASENAME: str = "data"
TRASH_DIR_BASENAME: str = "trash"
VERSIONS_DIR_BASENAME: str = "versions"
OLD_CODE_DIR_BASENAME: str = "old_code"
TEST_DATA_DIR_BASENAME: str = "test_data"
LOGS_DIR_BASENAME: str = "logs"
BACKUPS_DIR_BASENAME: str = "backups"
GIT_DIR_BASENAME: str = ".git"

# Project-relative paths built from the segment names above.
FILE_TRASH_RELATIVE_DIR: str = f"{DATA_DIR_BASENAME}/{TRASH_DIR_BASENAME}"
FILE_VERSIONS_RELATIVE_DIR: str = f"{DATA_DIR_BASENAME}/{VERSIONS_DIR_BASENAME}"

# Cache-like directory basenames: omitted from default ``list_project_files`` unless
# ``show_hidden`` (with dot-prefixed dirs, ``ls -a``-style); venv uses separate flags.
LISTING_CACHE_DIRECTORY_SEGMENTS: FrozenSet[str] = frozenset(
    {
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
    }
)

# Directory basenames: never descend in watcher / prune in project walks.
_DEFAULT_TRAVERSAL_SKIP_VENV_AND_TOOLING: FrozenSet[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        GIT_DIR_BASENAME,
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".nox",
        "nox",
        "eggs",
        ".eggs",
        "wheels",
        "htmlcov",
        "ENV",
        "env.bak",
        "venv.bak",
    }
)

# Server-managed / generated trees (backups, trash parent segments, logs).
_DEFAULT_TRAVERSAL_SKIP_SERVER_MANAGED: FrozenSet[str] = frozenset(
    {
        OLD_CODE_DIR_BASENAME,
        LOGS_DIR_BASENAME,
        BACKUPS_DIR_BASENAME,
        ".code_mapper_backups",
    }
)

DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES: FrozenSet[str] = (
    _DEFAULT_TRAVERSAL_SKIP_VENV_AND_TOOLING | _DEFAULT_TRAVERSAL_SKIP_SERVER_MANAGED
)

# Multi-segment path shapes skipped at watcher traversal time (not basename-only).
DEFAULT_TRAVERSAL_SKIP_ADJACENT_PATH_SEGMENT_PAIRS: FrozenSet[tuple[str, str]] = (
    frozenset(
        {
            (DATA_DIR_BASENAME, TRASH_DIR_BASENAME),
            (DATA_DIR_BASENAME, VERSIONS_DIR_BASENAME),
        }
    )
)

# Extra POSIX substrings for trash trees (defensive; pairs above are primary).
DEFAULT_TRAVERSAL_SKIP_POSIX_SUBPATH_MARKERS: FrozenSet[str] = frozenset(
    {f"/{FILE_TRASH_RELATIVE_DIR}/"}
)

# Basenames matched against path segments (POSIX) for ``is_ignored_project_relative_path``.
DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS: FrozenSet[str] = (
    DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES
)

_DEFAULT_IGNORED_FILE_SUFFIXES: FrozenSet[str] = frozenset(
    {".pyc", ".pyo", ".log", ".coverage"}
)

_DEFAULT_IGNORED_FILE_BASENAME_GLOBS: FrozenSet[str] = frozenset({"*.lock"})


def path_has_adjacent_segments(parts: tuple[str, ...], first: str, second: str) -> bool:
    """Return True when ``first`` is immediately followed by ``second`` in ``parts``."""
    for i in range(len(parts) - 1):
        if parts[i] == first and parts[i + 1] == second:
            return True
    return False


def path_matches_traversal_skip_shape_rules(
    parts: tuple[str, ...], posix_path: str
) -> bool:
    """
    True when ``parts``/``posix_path`` match multi-segment watcher skip rules.

    Used by :func:`code_analysis.core.file_watcher_pkg.scanner.should_skip_dir`
    for ``data/trash``, ``data/versions``, and related path-shape exclusions.
    """
    for seg_a, seg_b in DEFAULT_TRAVERSAL_SKIP_ADJACENT_PATH_SEGMENT_PAIRS:
        if path_has_adjacent_segments(parts, seg_a, seg_b):
            return True
    norm = posix_path if posix_path.endswith("/") else posix_path + "/"
    for marker in DEFAULT_TRAVERSAL_SKIP_POSIX_SUBPATH_MARKERS:
        if marker in norm:
            return True
    return False


def path_is_under_project_local_venv(resolved_path: Path, project_root: Path) -> bool:
    """
    True if ``resolved_path`` lies under ``project_root/.venv`` or ``project_root/venv``.
    """
    try:
        p = resolved_path.resolve()
        root = project_root.resolve()
    except OSError:
        return False
    for name in (".venv", "venv"):
        try:
            anchor = (root / name).resolve()
            p.relative_to(anchor)
            return True
        except ValueError:
            continue
        except OSError:
            continue
    return False


def is_ignored_project_relative_path(
    relative_posix: str,
    *,
    include_venv: bool = False,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
) -> bool:
    """
    Return True when a project-relative POSIX path should be hidden from normal listing.

    Used by ``list_project_files`` and tests. When ``include_venv`` is True, paths
    under a ``.venv`` or ``venv`` segment are not ignored by this helper (caller may
    still restrict to allowlisted RECORD paths). When ``include_venv_ignore_exceptions``
    is True, paths under venv are not ignored here so ``ignore_exceptions`` expansions
    can appear in diagnostic listings. When ``show_hidden`` is True (``ls -a``-style),
    paths under dot-prefixed directory segments (except ``.venv``/``venv``) and under
    :data:`LISTING_CACHE_DIRECTORY_SEGMENTS` are not ignored for those segments.
    """
    rel = (relative_posix or "").strip().replace("\\", "/").strip("/")
    if not rel:
        return False
    parts = tuple(x for x in rel.split("/") if x)
    if path_matches_traversal_skip_shape_rules(parts, rel):
        return True
    for seg in parts:
        if seg in DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS:
            if seg in (".venv", "venv") and (
                include_venv or include_venv_ignore_exceptions
            ):
                continue
            if seg in LISTING_CACHE_DIRECTORY_SEGMENTS and show_hidden:
                continue
            if show_hidden and seg.startswith(".") and seg not in (".venv", "venv"):
                continue
            return True
    base = parts[-1] if parts else ""
    low = base.lower()
    for suf in _DEFAULT_IGNORED_FILE_SUFFIXES:
        if low.endswith(suf):
            return True
    for pat in _DEFAULT_IGNORED_FILE_BASENAME_GLOBS:
        if fnmatch.fnmatch(base, pat):
            return True
    return False


def sql_and_absolute_path_eligible_for_default_status_aggregates(
    path_column: str,
) -> str:
    """
    Portable SQL AND-fragment so aggregates match "normal" project paths.

    ``files.path`` is absolute; this mirrors :func:`is_ignored_project_relative_path`
    for directory basenames in :data:`DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS` by
    requiring a ``/segment/`` boundary (or end/start) so arbitrary substring
    false positives stay unlikely.

    Append to ``WHERE`` clauses that should exclude virtualenvs, VCS trees, caches,
    etc. from ``get_database_status`` needing_* counts and samples.
    """
    parts: list[str] = []
    for seg in sorted(DEFAULT_IGNORED_RELATIVE_DIR_SEGMENTS):
        esc = seg.replace("'", "''")
        parts.append(
            "("
            f"{path_column} LIKE '%/{esc}/%' OR {path_column} LIKE '%/{esc}' "
            f"OR {path_column} LIKE '{esc}/%' OR {path_column} = '{esc}'"
            ")"
        )
    inner = " OR ".join(parts)
    return f" AND NOT ({inner}) "


def filter_paths_for_default_project_listing(
    paths: Collection[Path],
    project_root: Path,
    *,
    include_venv: bool,
    include_venv_ignore_exceptions: bool,
    show_hidden: bool = False,
    already_resolved: bool = False,
) -> list[Path]:
    """Drop ignored relative paths; used when assembling ``list_project_files`` results.

    ``already_resolved=True`` skips the per-path ``Path.resolve()`` call -- pass it
    ONLY when every path in ``paths`` and ``project_root`` are already fully
    resolved (e.g. :func:`enumerate_project_paths`'s own ``uniq``/``ordered``
    pipeline). Default ``False`` preserves the original always-resolve behavior
    for any other caller.
    """
    root = project_root if already_resolved else project_root.resolve()
    out: list[Path] = []
    for p in paths:
        try:
            rp = p if already_resolved else p.resolve()
            rel = rp.relative_to(root).as_posix()
        except ValueError:
            continue
        except OSError:
            continue
        if is_ignored_project_relative_path(
            rel,
            include_venv=include_venv,
            include_venv_ignore_exceptions=include_venv_ignore_exceptions,
            show_hidden=show_hidden,
        ):
            continue
        out.append(p)
    return out


def filter_ignore_exception_py_paths_for_watcher(
    paths: AbstractSet[Path],
    project_roots: Collection[Path],
    allowed_venv_py_files: Optional[AbstractSet[Path]],
) -> set[Path]:
    """
    Drop ``ignore_exceptions`` targets that live under a project venv unless allowlisted.

    Watcher merge still indexes allowlisted RECORD ``.py`` under site-packages; broad
    ``ignore_exceptions`` globs under ``.venv`` must not pull entire site-packages trees.
    """
    allowed = allowed_venv_py_files or frozenset()
    roots = [Path(pr).resolve() for pr in project_roots]
    out: set[Path] = set()
    for p in paths:
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp in allowed:
            out.add(rp)
            continue
        under_venv = False
        for root in roots:
            if path_is_under_project_local_venv(rp, root):
                under_venv = True
                break
        if under_venv:
            continue
        out.add(rp)
    return out
