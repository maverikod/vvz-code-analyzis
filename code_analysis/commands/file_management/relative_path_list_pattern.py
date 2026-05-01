"""
Project-relative path glob matching for listing commands (list_project_files, backups, etc.).

Shell-style :func:`fnmatch.fnmatch` on normalized POSIX strings; literals without ``*?[]``
match exactly or as a directory prefix (``path == pat`` or, after stripping a trailing
``/`` from ``pat``, ``path == pat`` or ``path.startswith(pat + "/")``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from pathlib import Path


def canonical_relative_path(project_root: Path, absolute_path: Path) -> str:
    """Stable posix path from ``project_root`` for FS/DB joins.

    Args:
        project_root: Project root directory.
        absolute_path: Absolute path to resolve relative to project root.

    Returns:
        Posix relative path if ``absolute_path`` is under ``project_root``,
        otherwise absolute posix path.
    """
    try:
        return absolute_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return absolute_path.resolve().as_posix()


def normalize_listing_pattern(raw: str) -> str:
    """Normalize user-supplied path/glob (trim, ``\\\\`` → ``/``, strip ``./``)."""
    s = str(raw).strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    return s


def pattern_has_fnmatch_magic(pattern: str) -> bool:
    """Return True if ``pattern`` uses fnmatch metacharacters."""
    return any(ch in pattern for ch in "*?[]")


def relative_path_matches_listing_pattern(
    relative_posix: str, file_pattern: str
) -> bool:
    """Match ``file_pattern`` against a path string (usually project-relative POSIX).

    When the pattern contains no fnmatch metacharacters, it is treated as an exact path or
    a directory prefix. Otherwise :func:`fnmatch.fnmatch` is used (POSIX: ``*`` matches
    ``/``). The same rules apply if ``relative_posix`` is an absolute path string, as long
    as both sides use consistent ``/`` normalization.

    Args:
        relative_posix: Path string to test (posix, normalized by caller if needed).
        file_pattern: User-supplied glob or prefix.

    Returns:
        True if the path matches.
    """
    pat = normalize_listing_pattern(file_pattern)
    if not pat:
        return True
    if not pattern_has_fnmatch_magic(pat):
        # Trailing "/" is directory notation; ``pat + "/"`` would double the slash
        # and break prefix matching (e.g. ``code_analysis/commands/``).
        if relative_posix == pat:
            return True
        pat_core = pat.rstrip("/")
        if pat_core:
            return relative_posix == pat_core or relative_posix.startswith(
                pat_core + "/"
            )
        return False
    return fnmatch.fnmatch(relative_posix, pat)


def effective_listing_pattern(file_pattern: str | None, glob: str | None) -> str | None:
    """Resolve ``file_pattern`` vs ``glob`` (non-empty ``file_pattern`` wins)."""
    if file_pattern and str(file_pattern).strip():
        return str(file_pattern).strip()
    if glob and str(glob).strip():
        return str(glob).strip()
    return None
