"""
Container watch-directory path layout for Docker deployments.

Each watch root is mounted at ``{CASMGR_DOCKER_WATCH_ROOT}/{watch_dir_id}``.
The same path is stored in ``watch_dir_paths.absolute_path`` and used in
``code_analysis.worker.watch_dirs[].path``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from code_analysis.core.constants import CASMGR_DOCKER_WATCH_ROOT


def docker_watch_dir_container_path(
    watch_dir_id: str,
    *,
    watch_root: str = CASMGR_DOCKER_WATCH_ROOT,
) -> str:
    """
    Return the canonical container path for a watch directory UUID.

    Example: ``/watched/a6c47e01-1ac8-47a6-a0e8-e6416086de0c``
    """
    wid = (watch_dir_id or "").strip()
    if not wid:
        raise ValueError("watch_dir_id is required")
    root = (watch_root or CASMGR_DOCKER_WATCH_ROOT).rstrip("/")
    return f"{root}/{wid}"


def normalize_docker_watch_path(path: str) -> str:
    """Normalize a watch path for comparison (POSIX, no trailing slash)."""
    return Path(path).as_posix().rstrip("/")


def is_under_docker_watch_root(
    path: str,
    *,
    watch_root: str = CASMGR_DOCKER_WATCH_ROOT,
) -> bool:
    """True when ``path`` is under the container watch root."""
    try:
        root = Path(watch_root).resolve()
        candidate = Path(path).resolve()
    except (OSError, ValueError):
        root_p = Path(normalize_docker_watch_path(watch_root))
        cand_p = Path(normalize_docker_watch_path(path))
        return cand_p == root_p or str(cand_p).startswith(str(root_p) + "/")
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def expected_path_for_watch_dir_id(
    watch_dir_id: str,
    *,
    watch_root: Optional[str] = None,
) -> str:
    """Alias for :func:`docker_watch_dir_container_path` (explicit name for validators)."""
    root = watch_root if watch_root is not None else CASMGR_DOCKER_WATCH_ROOT
    return docker_watch_dir_container_path(watch_dir_id, watch_root=root)


def validate_docker_watch_dir_entry(
    watch_dir_id: str,
    path: str,
    *,
    watch_root: Optional[str] = None,
) -> Optional[str]:
    """
    Return an error message when ``path`` does not match ``{root}/{id}``.

    When ``path`` is not under ``watch_root``, returns ``None`` (host deployment).
    """
    root = watch_root if watch_root is not None else CASMGR_DOCKER_WATCH_ROOT
    if not is_under_docker_watch_root(path, watch_root=root):
        return None
    expected = normalize_docker_watch_path(
        expected_path_for_watch_dir_id(watch_dir_id, watch_root=root)
    )
    actual = normalize_docker_watch_path(path)
    if actual != expected:
        return (
            f"watch_dirs path must equal {expected!r} for id {watch_dir_id!r} "
            f"(got {actual!r}; DB watch_dir_paths.absolute_path uses config path)"
        )
    return None


def docker_watch_root_from_env() -> str:
    """Resolve watch root from ``CASMGR_WATCH_ROOT`` or default ``/watched``."""
    return os.environ.get("CASMGR_WATCH_ROOT", CASMGR_DOCKER_WATCH_ROOT).strip() or (
        CASMGR_DOCKER_WATCH_ROOT
    )
