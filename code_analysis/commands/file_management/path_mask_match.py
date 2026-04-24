"""
Match project-relative paths against a user mask (prefix, rm-like globs, or **).

All masks and match targets are interpreted as if the **current directory were the
project root** (``projects.root_path``), not the process ``cwd``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Dict, List


def normalize_path_mask_for_project(mask: str) -> str:
    """
    Normalize a user-supplied mask relative to the project root.

    - Strips surrounding whitespace.
    - Converts backslashes to forward slashes.
    - Strips **all** leading ``/`` characters: each ``/`` only anchors to the project
      root, not the host filesystem. So ``*``, ``/*``, and ``//*`` are the same mask;
      ``foo`` and ``/foo`` and ``//foo`` are the same.

    Matching is always against paths produced by :func:`relative_path_posix` (no
    leading slash, relative to ``projects.root_path``).
    """
    s = mask.strip().replace("\\", "/")
    while s.startswith("/"):
        s = s[1:]
    return s


def relative_path_posix(project_root: Path, absolute_path: str) -> str:
    """Path of file relative to project root, forward slashes, no leading slash."""
    root = project_root.resolve()
    ap = Path(absolute_path).resolve()
    try:
        rel = ap.relative_to(root)
    except ValueError:
        rel = Path(absolute_path)
    s = rel.as_posix().lstrip("/")
    return s


def path_matches_mask(rel_posix: str, mask: str) -> bool:
    """
    Return True if ``rel_posix`` (relative to project root) matches ``mask``.

    ``mask`` is normalized with :func:`normalize_path_mask_for_project` so a
    leading ``/`` denotes the project root (same as ``rm`` working from project
    root, not host ``/``).

    **Prefix (no** ``* ? [`` **in mask):** path equals ``mask`` or starts with
    ``mask/`` (after stripping a trailing slash on ``mask``). Deletes a whole
    subtree, e.g. ``build`` or ``build/``.

    **Rm-style single-component glob:** if the mask contains ``* ? [`` but no
    ``/``, only the **first** path segment is matched against the whole pattern
    (``*`` and ``?`` do not cross ``/``, like plain ``sh`` / ``rm`` globs). Example:
    ``tes*`` matches ``testing/foo.py`` (first segment ``testing``) and
    ``tes_file.py``, but not ``src/test.py``.

    **Path glob (contains** ``/`` **):** split on ``/``; segment ``**`` matches
    zero or more path segments; other segments use :func:`fnmatch.fnmatchcase`.
    A trailing ``**`` matches any remaining path.
    """
    rel = rel_posix.replace("\\", "/").strip("/")
    mask_norm = normalize_path_mask_for_project(mask)
    if not mask_norm:
        return False

    if not any(ch in mask_norm for ch in "*?["):
        prefix = mask_norm.rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")

    # rm-style: wildcards but no "/" — pattern applies only to the first path component
    if "/" not in mask_norm:
        if not rel:
            return False
        first_seg = rel.split("/")[0]
        return fnmatch.fnmatchcase(first_seg, mask_norm)

    mask_parts = [p for p in mask_norm.split("/") if p != ""]
    if not mask_parts:
        return False
    rel_parts = rel.split("/") if rel else []

    return _match_parts(rel_parts, mask_parts)


def _match_parts(rel_parts: List[str], mask_parts: List[str]) -> bool:
    from functools import lru_cache

    n_rel = len(rel_parts)
    n_mask = len(mask_parts)

    @lru_cache(maxsize=None)
    def dfs(ri: int, mi: int) -> bool:
        if mi == n_mask:
            return ri == n_rel
        mp = mask_parts[mi]
        if mp == "**":
            if mi + 1 == n_mask:
                return True
            if dfs(ri, mi + 1):
                return True
            if ri < n_rel and dfs(ri + 1, mi):
                return True
            return False
        if ri >= n_rel:
            return False
        if fnmatch.fnmatchcase(rel_parts[ri], mp):
            return dfs(ri + 1, mi + 1)
        return False

    return dfs(0, 0)


def filter_rows_by_mask(
    rows: List[Dict[str, Any]],
    project_root: Path,
    path_mask: str,
) -> List[Dict[str, Any]]:
    """Keep file rows whose path matches ``path_mask`` relative to ``project_root``."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        path = row.get("path")
        if not path or not isinstance(path, str):
            continue
        try:
            rel = relative_path_posix(project_root, path)
        except OSError:
            rel = Path(path).as_posix()
        if path_matches_mask(rel, path_mask):
            out.append(row)
    return out
