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
    path_is_under_project_local_venv,
)
from ..core.venv_path_policy import (
    build_allowlisted_site_packages_py_files,
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
    uniq = {p.resolve() for p in found}
    ordered = sorted(uniq, key=lambda p: canonical_relative_path(root, p))
    return filter_paths_for_default_project_listing(
        ordered,
        root,
        include_venv=show_venv,
        include_venv_ignore_exceptions=include_venv_ignore_exceptions,
        show_hidden=show_hidden,
    )
