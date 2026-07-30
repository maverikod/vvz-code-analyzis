"""
Filesystem enumeration under a project root (ls / grep / FS tools).

Shared with ``list_project_files`` and ``fs_grep`` — no database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Collection, Dict, List, Optional, Tuple

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

from .file_management.relative_path_list_pattern import (
    canonical_relative_path,
    static_prefix_of_listing_pattern,
)


def _resolve_scope_root_for_request_pattern(
    root: Path,
    request_static_prefix: Optional[str],
    *,
    show_hidden: bool,
) -> Path:
    """Return the safe ``os.walk`` start directory for ``request_static_prefix``.

    Falls back to ``root`` (no scoping -- full-tree walk, today's behavior)
    whenever the prefix is absent, escapes ``root``, does not exist as a
    directory, or any of its path segments (ancestors AND the leaf itself)
    would be pruned by the default project walk. The leaf check matters as
    much as the ancestor checks: ``os.walk`` never re-applies its own
    ``dirs``-list pruning rule to the directory it was told to start at, only
    to entries it discovers while descending, so pointing it directly at an
    otherwise-ignored directory (e.g. a request pattern naming a path under
    ``node_modules``) would silently surface paths a full walk from ``root``
    would never reach -- conservativeness (condition 3a) requires ``root`` in
    every such doubtful case, never a guess.

    Args:
        root: Already-resolved project root.
        request_static_prefix: Return value of
            :func:`static_prefix_of_listing_pattern` for the effective
            request pattern, or ``None`` when no pattern / no derivable
            prefix.
        show_hidden: Same flag the walk itself will use, so the safety check
            agrees with the walk's own dot-dir/cache-dir pruning rule.

    Returns:
        ``root / request_static_prefix`` (resolved) when every segment is
        provably reachable by the default walk, else ``root`` unchanged.
    """
    if not request_static_prefix:
        return root
    try:
        candidate = (root / request_static_prefix).resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return root
    try:
        if not candidate.is_dir():
            return root
    except OSError:
        return root
    ignore_dirs = default_project_walk_prune_ignore_dir_basenames()
    for seg in request_static_prefix.strip("/").split("/"):
        if not seg:
            continue
        if directory_basename_pruned_from_default_project_walk(
            seg, ignore_dirs, show_hidden=show_hidden
        ):
            return root
    return candidate


def _prefixes_may_overlap(a: str, b: str) -> bool:
    """True when directory-prefix strings ``a``/``b`` could describe overlapping subtrees.

    ``a`` may overlap ``b`` when they are equal or one is an ancestor
    directory of the other (a ``/``-bounded prefix, not a bare string
    prefix -- ``docs/plan`` must NOT be treated as overlapping ``docs/plans``).
    """
    if a == b:
        return True
    return a.startswith(b + "/") or b.startswith(a + "/")


def _select_ignore_exceptions_relevant_to_request(
    patterns: Collection[str], request_static_prefix: Optional[str]
) -> List[str]:
    """Conservative pre-filter over ``ignore_exceptions`` glob patterns to expand.

    Performance-only optimization (bug 25c8d9dd): every file an EXCLUDED
    pattern could ever expand to is later dropped anyway by the caller's own
    pattern-match filter over the merged result, so skipping its (potentially
    expensive) glob expansion here changes nothing about the final result --
    provided the exclusion is provably safe. A pattern is excluded ONLY when
    both its own derivable static prefix and ``request_static_prefix`` are
    known non-empty strings AND neither is an ancestor of the other (see
    :func:`_prefixes_may_overlap`); a pattern whose own prefix cannot be
    derived (``None``, e.g. ``*.env``) is always expanded, matching the
    pre-25c8d9dd unconditional behavior for it. When ``request_static_prefix``
    itself is ``None`` (no derivable request-pattern prefix, or no pattern at
    all), every pattern is expanded unconditionally -- unchanged behavior.

    Args:
        patterns: Raw ``code_analysis.ignore_exceptions`` glob patterns.
        request_static_prefix: Return value of
            :func:`static_prefix_of_listing_pattern` for the effective
            request pattern.

    Returns:
        The subset of ``patterns`` that must still be expanded.
    """
    if not request_static_prefix:
        return list(patterns)
    selected: List[str] = []
    for pat in patterns:
        pat_prefix = static_prefix_of_listing_pattern(pat)
        if not pat_prefix or _prefixes_may_overlap(pat_prefix, request_static_prefix):
            selected.append(pat)
    return selected


# --- bug 8e6acb34: bounded, disk-accurate, single-flight enumeration cache ---
#
# DESIGN DECISION (bug 8e6acb34, steps 3-5). ``list_project_files``/``fs_grep``
# pay for a full ``os.walk`` of the project tree on EVERY call regardless of
# ``page_size`` -- measured concurrency speedup for ``page_size=1`` was 0.80x
# on the deployed server (should overlap, does not), with the walk's Python-
# level per-path filtering/sorting holding the GIL for ~0.39s/call (36.6x the
# exact-file fast path's cost).
#
# THE OBVIOUS ALTERNATIVE -- make the ``files`` DB table (already maintained
# by the watcher) the source of truth instead of walking disk -- was
# EVALUATED AND REJECTED after measurement, not assumed away:
#   * The watcher only inserts rows whose suffix is in ``CODE_FILE_EXTENSIONS``
#     (``core/constants.py`` -- currently exactly ``{".py"}``, comment: "Only
#     .py is indexed (AST/CST); other extensions were causing index errors")
#     plus opt-in docs-eligible ``.md``/``.json``/``.yaml``/``.yml``.
#   * A DEFAULT listing (``python_only=False``) -- the EXACT mode this bug's
#     own regression check (``lifecycle_read_throughput.py``, ``page_size=1``,
#     no ``file_pattern``) exercises -- would silently drop every ordinary
#     project file that is not ``.py`` or docs-eligible: ``.txt``, ``.cfg``,
#     ``.ini``, ``.toml``, ``.sh``, ``.sql``, ``Dockerfile``, ``LICENSE``, ...
#     i.e. most of a typical project. That is not a staleness trade-off, it
#     is MISSING DATA in the common case -- a fast, wrong answer, which this
#     bug's own remediation brief rules out ("a correct 0.39s listing beats a
#     wrong 0.01s one").
#   * The watcher's own freshness bound is also weaker than it first looks:
#     default ``scan_interval`` is 60s, backing off to up to 3600s when idle
#     (``file_watcher_pkg/scan_interval_backoff.py``), and the watcher can be
#     disabled entirely in config with nothing in the read path gating on its
#     liveness.
#
# INSTEAD: cache the WALK RESULT itself (still disk-truth, still covers every
# extension, still applies every existing filter unchanged) for a short TTL,
# single-flight per cache key, so repeat calls with IDENTICAL parameters --
# the exact shape both this bug's own concurrency check and ordinary agent
# "list, then list again" traffic produce -- pay for one walk instead of N.
# A cache MISS runs the unmodified pre-existing code path (byte-identical
# result, same ordering, same envelope). A cache HIT is bounded to
# ``_ENUMERATION_CACHE_TTL_SECONDS`` staleness -- far tighter than the
# watcher's own 60s-3600s window -- and only ever serves the SAME (root,
# filters, pattern) tuple a caller already asked for, never a different data
# source. This also naturally covers ``fs_grep``, which calls
# :func:`enumerate_project_paths` directly with the same signature.
_ENUMERATION_CACHE_TTL_SECONDS = 2.0
_ENUMERATION_CACHE_MAX_ENTRIES = 256

# (resolved root, show_venv, python_only, include_venv_ignore_exceptions,
# show_hidden, request_pattern)
_EnumerationCacheKey = Tuple[str, bool, bool, bool, bool, Optional[str]]

_enumeration_cache: "OrderedDict[_EnumerationCacheKey, Tuple[float, List[Path]]]" = (
    OrderedDict()
)
_enumeration_cache_guard = threading.Lock()
_enumeration_key_locks: Dict[_EnumerationCacheKey, threading.Lock] = {}


def clear_enumeration_cache() -> None:
    """Drop every cached enumeration result.

    Test-isolation hook (a fresh ``tmp_path`` per test already gives a
    distinct cache key, but callers that reuse a root across cases, or that
    need to assert a cache MISS deterministically, can call this first) and
    an explicit invalidation point for any future caller that needs to force
    a fresh walk instead of waiting out the TTL.
    """
    with _enumeration_cache_guard:
        _enumeration_cache.clear()
        _enumeration_key_locks.clear()


def _enumeration_cache_get(key: _EnumerationCacheKey) -> Optional[List[Path]]:
    """Return a fresh-enough cached result for ``key``, else ``None``."""
    now = time.monotonic()
    with _enumeration_cache_guard:
        entry = _enumeration_cache.get(key)
        if entry is not None and (now - entry[0]) < _ENUMERATION_CACHE_TTL_SECONDS:
            _enumeration_cache.move_to_end(key)
            return list(entry[1])
    return None


def _enumeration_cache_put(key: _EnumerationCacheKey, paths: List[Path]) -> None:
    """Store ``paths`` for ``key``, evicting the oldest entry over capacity."""
    with _enumeration_cache_guard:
        _enumeration_cache[key] = (time.monotonic(), list(paths))
        _enumeration_cache.move_to_end(key)
        while len(_enumeration_cache) > _ENUMERATION_CACHE_MAX_ENTRIES:
            _enumeration_cache.popitem(last=False)


def _enumeration_key_lock(key: _EnumerationCacheKey) -> threading.Lock:
    """Return the single-flight lock for ``key``, creating it if needed."""
    with _enumeration_cache_guard:
        lock = _enumeration_key_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _enumeration_key_locks[key] = lock
        return lock


def enumerate_project_paths(
    project_root: Path,
    show_venv: bool,
    *,
    python_only: bool,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
    request_pattern: Optional[str] = None,
) -> List[Path]:
    """Return sorted absolute file paths under ``project_root`` (listing policy).

    Same rules as legacy ``list_project_files`` walk: skip venv by default, optional
    allowlisted site-packages ``.py``, ignore_exceptions expansion, cache/hidden policy.

    A short-TTL, single-flight, disk-accurate cache sits in front of the walk
    (bug 8e6acb34) -- see the module-level comment above this function for
    why the walk itself, not the DB index, remains the source of truth, and
    :data:`_ENUMERATION_CACHE_TTL_SECONDS` for the staleness bound. Call
    :func:`clear_enumeration_cache` to force a fresh walk.

    Args:
        project_root: Project root directory.
        show_venv: Include allowlisted venv site-packages ``.py`` files.
        python_only: Restrict the walk to ``.py`` files.
        include_venv_ignore_exceptions: Include ``ignore_exceptions`` matches
            that live under ``.venv``/``venv``.
        show_hidden: ``ls -a``-style dot-dir/cache-dir inclusion.
        request_pattern: Optional raw ``file_pattern``/``glob`` value the
            caller will filter the result against afterward (bug 25c8d9dd).
            When its static prefix (:func:`static_prefix_of_listing_pattern`)
            resolves to a safely-reachable existing directory, the walk is
            bounded to that subtree instead of the whole project root, and
            ``ignore_exceptions`` glob expansion is pre-filtered to patterns
            that could plausibly land inside it (see
            :func:`_select_ignore_exceptions_relevant_to_request`). Passing
            ``None`` (default) reproduces the pre-25c8d9dd full-root-walk,
            expand-everything behavior exactly.
    """
    root = project_root.resolve()
    cache_key: _EnumerationCacheKey = (
        str(root),
        bool(show_venv),
        bool(python_only),
        bool(include_venv_ignore_exceptions),
        bool(show_hidden),
        request_pattern,
    )
    cached = _enumeration_cache_get(cache_key)
    if cached is not None:
        return cached
    lock = _enumeration_key_lock(cache_key)
    with lock:
        # Re-check: another thread may have just filled this key while this
        # one was waiting on the lock (single-flight -- only one walk runs
        # per key per TTL window even under concurrent callers).
        cached = _enumeration_cache_get(cache_key)
        if cached is not None:
            return cached
        result = _enumerate_project_paths_uncached(
            root,
            show_venv,
            python_only=python_only,
            include_venv_ignore_exceptions=include_venv_ignore_exceptions,
            show_hidden=show_hidden,
            request_pattern=request_pattern,
        )
        _enumeration_cache_put(cache_key, result)
        return list(result)


def _enumerate_project_paths_uncached(
    project_root: Path,
    show_venv: bool,
    *,
    python_only: bool,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
    request_pattern: Optional[str] = None,
) -> List[Path]:
    """Unmodified pre-8e6acb34-fix walk. See :func:`enumerate_project_paths`."""
    root = project_root.resolve()
    request_static_prefix = (
        static_prefix_of_listing_pattern(request_pattern) if request_pattern else None
    )
    scope_root = _resolve_scope_root_for_request_pattern(
        root, request_static_prefix, show_hidden=show_hidden
    )
    found: List[Path]
    if python_only:
        found = list(
            iter_project_python_files_excluding_venv(
                root, show_hidden=show_hidden, scope_root=scope_root
            )
        )
        exc_expand = expand_ignore_exception_py_files
    else:
        found = list(
            iter_project_files_excluding_venv(
                root, show_hidden=show_hidden, scope_root=scope_root
            )
        )
        exc_expand = expand_ignore_exception_all_files
    if show_venv:
        allowlist = load_venv_site_packages_index_allowlist_from_config()
        found.extend(build_allowlisted_site_packages_py_files(root, allowlist))
    exc_patterns = load_ignore_exceptions_from_config()
    if exc_patterns:
        relevant_patterns = _select_ignore_exceptions_relevant_to_request(
            exc_patterns, request_static_prefix
        )
        extra = list(exc_expand(root, relevant_patterns))
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
