"""
Filesystem enumeration under a project root (ls / grep / FS tools).

Shared with ``list_project_files`` and ``fs_grep`` — no database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from ..core.project_ignore_policy import (
    filter_paths_for_default_project_listing,
    is_ignored_project_relative_path,
    path_is_under_project_local_venv,
)
from ..core.venv_path_policy import (
    LIST_PROJECT_SKIP_FILE_SUFFIXES,
    build_allowlisted_site_packages_py_files,
    default_project_walk_prune_ignore_dir_basenames,
    directory_basename_pruned_from_default_project_walk,
    expand_ignore_exception_all_files,
    expand_ignore_exception_py_files,
    iter_project_files_excluding_venv,
    iter_project_python_files_excluding_venv,
    load_ignore_exceptions_from_config,
    load_venv_site_packages_index_allowlist_from_config,
)

from .file_management.relative_path_list_pattern import canonical_relative_path


def enumerate_project_paths(
    project_root: Path,
    show_venv: bool,
    *,
    python_only: bool,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
) -> List[Path]:
    """Return sorted absolute file paths under ``project_root`` (listing policy).

    Same rules as legacy ``list_project_files`` walk: skip venv by default, optional
    allowlisted site-packages ``.py``, ignore_exceptions expansion, cache/hidden policy.
    """
    root = project_root.resolve()
    found: List[Path]
    if python_only:
        found = list(
            iter_project_python_files_excluding_venv(root, show_hidden=show_hidden)
        )
        exc_expand = expand_ignore_exception_py_files
    else:
        found = list(iter_project_files_excluding_venv(root, show_hidden=show_hidden))
        exc_expand = expand_ignore_exception_all_files
    if show_venv:
        allowlist = load_venv_site_packages_index_allowlist_from_config()
        found.extend(build_allowlisted_site_packages_py_files(root, allowlist))
    exc_patterns = load_ignore_exceptions_from_config()
    if exc_patterns:
        extra = list(exc_expand(root, exc_patterns))
        if not include_venv_ignore_exceptions:
            extra = [
                p
                for p in extra
                if not path_is_under_project_local_venv(p.resolve(), root)
            ]
        found.extend(extra)
    # ``found`` is already canonical for every source: the walk builds paths by
    # joining onto the already-resolved ``root`` (os.walk never traverses through
    # a symlinked directory, so no ".." / symlink component can appear along the
    # way) and every non-walk source (allowlisted venv RECORD paths,
    # ignore_exceptions expansion) already calls ``.resolve()`` internally before
    # returning. The one exception is a *leaf* symlink -- a regular file entry
    # discovered by the walk that is itself a symlink -- whose apparent (walked)
    # path differs from its real target; only that case still needs resolving,
    # so limit the (expensive, full-path realpath) ``.resolve()`` call to it via
    # a cheap ``is_symlink()`` probe (single lstat) instead of unconditionally
    # resolving all N paths.
    uniq: set[Path] = set()
    for p in found:
        try:
            uniq.add(p.resolve() if p.is_symlink() else p)
        except OSError:
            uniq.add(p)
    ordered = sorted(
        uniq, key=lambda p: canonical_relative_path(root, p, already_resolved=True)
    )
    return filter_paths_for_default_project_listing(
        ordered,
        root,
        include_venv=show_venv,
        include_venv_ignore_exceptions=include_venv_ignore_exceptions,
        show_hidden=show_hidden,
        already_resolved=True,
    )


def path_survives_default_project_listing_filter(
    relative_posix: str,
    *,
    python_only: bool,
    show_hidden: bool,
) -> bool:
    """True when a single discovered ``relative_posix`` would survive the same
    per-path filters a full :func:`enumerate_project_paths` walk applies:

    1. Ancestor-directory walk pruning (:func:`directory_basename_pruned_from_
       default_project_walk`, per ancestor segment) -- this is where generic
       ``ls -a`` dot-directory hiding actually happens for the real walk; it is
       NOT re-derived from :func:`is_ignored_project_relative_path`, whose
       per-segment dot-dir rule only covers a fixed named set, not arbitrary
       dot dirs. Getting this wrong would fast-path a hidden file as a false hit
       when ``show_hidden`` is false and the walk would never have discovered it.
    2. The ``python_only`` extension gate.
    3. The binary/bytecode suffix skip (:data:`LIST_PROJECT_SKIP_FILE_SUFFIXES`,
       non-``python_only`` mode only).
    4. :func:`is_ignored_project_relative_path` (known heavy-tree segment names,
       adjacent-pair shapes like ``data/trash``, ignored file suffixes/globs).

    Reused by any single-path fast path (e.g. ``list_project_files`` exact-file
    ``file_pattern`` lookup) so this rule set lives in exactly one place -- do
    not reimplement it at a call site.

    Always evaluates step 4 as if ``show_venv=False`` and
    ``include_venv_ignore_exceptions=False`` (belt-and-suspenders: step 1 already
    prunes every ``.venv``/``venv`` ancestor unconditionally). Deciding whether a
    venv path is genuinely reachable requires either RECORD-based site-packages
    parsing (:func:`build_allowlisted_site_packages_py_files`) or
    ``ignore_exceptions`` config-glob expansion -- both are walk-level, multi-path
    mechanisms this single-path predicate does not replicate. Likewise does NOT
    evaluate non-venv ``ignore_exceptions`` overrides: a path this returns
    ``False`` for may still be reachable via such an expansion. Callers needing
    an exact single-path verdict must treat ``False`` as "cannot prove
    reachable by the fast per-path rules" (fall back to the full walk), never as
    a hard exclusion verdict in its own right.
    """
    parts = [seg for seg in relative_posix.split("/") if seg]
    if len(parts) > 1:
        ignore_dirs = default_project_walk_prune_ignore_dir_basenames()
        for seg in parts[:-1]:
            if directory_basename_pruned_from_default_project_walk(
                seg, ignore_dirs, show_hidden=show_hidden
            ):
                return False
    if python_only:
        if not relative_posix.endswith(".py"):
            return False
    else:
        suffix = Path(relative_posix).suffix.lower()
        if suffix in LIST_PROJECT_SKIP_FILE_SUFFIXES:
            return False
    return not is_ignored_project_relative_path(
        relative_posix,
        include_venv=False,
        include_venv_ignore_exceptions=False,
        show_hidden=show_hidden,
    )
