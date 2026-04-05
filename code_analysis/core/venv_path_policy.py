"""
Project-local virtualenv (.venv / venv) path policy for indexing and writes.

- Indexing may include only allowlisted pip *distribution* names under site-packages,
  resolved via *.dist-info METADATA + RECORD (see docs).
- Any resolved path under the project’s ``.venv`` or ``venv`` directory is treated as
  read-only for server-driven writes (CST, text, JSON, line replace).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Collection, FrozenSet, List, Optional, Set

logger = logging.getLogger(__name__)


def normalize_pep503_distribution_name(name: str) -> str:
    """
    Normalize a distribution name per PEP 503 (case-insensitive; - _ . equivalent).

    Used to compare pip distribution names from METADATA ``Name:`` with config allowlist.
    """
    s = name.strip()
    if not s:
        return ""
    s = re.sub(r"[-_.]+", "-", s)
    return s.lower()


def _resolve_config_path() -> Path:
    """Best-effort path to the active server config.json (same strategy as BaseMCPCommand)."""
    try:
        from mcp_proxy_adapter.config import get_config

        cfg = get_config()
        cfg_path = getattr(cfg, "config_path", None)
        if isinstance(cfg_path, str) and cfg_path.strip():
            return Path(cfg_path).expanduser().resolve()
    except Exception:
        pass
    return (Path.cwd() / "config.json").resolve()


def load_venv_site_packages_index_allowlist_from_config() -> List[str]:
    """
    Return ``code_analysis.venv_site_packages_index_allowlisted_distributions`` from config.

    Missing or invalid entries yield an empty list (only project sources are indexed;
    venv remains skipped).
    """
    try:
        from .storage_paths import load_raw_config

        raw = load_raw_config(_resolve_config_path())
        ca = raw.get("code_analysis") or {}
        val = ca.get("venv_site_packages_index_allowlisted_distributions")
        if val is None:
            return []
        if not isinstance(val, list):
            logger.warning(
                "venv_site_packages_index_allowlisted_distributions must be a list; ignoring"
            )
            return []
        out: List[str] = []
        for item in val:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    except Exception as e:
        logger.debug("Could not load venv index allowlist from config: %s", e)
        return []


def path_is_under_project_local_venv(resolved_path: Path, project_root: Path) -> bool:
    """
    True if ``resolved_path`` lies under ``project_root/.venv`` or ``project_root/venv``.

    Uses :meth:`Path.resolve` for both paths when possible.
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


def iter_site_packages_dirs(project_root: Path) -> List[Path]:
    """Return existing ``site-packages`` directories under ``.venv`` and ``venv``."""
    found: List[Path] = []
    root = project_root.resolve()
    for vname in (".venv", "venv"):
        vbase = root / vname
        if not vbase.is_dir():
            continue
        lib = vbase / "lib"
        if not lib.is_dir():
            continue
        try:
            for child in lib.iterdir():
                if child.is_dir() and child.name.startswith("python"):
                    sp = child / "site-packages"
                    if sp.is_dir():
                        found.append(sp.resolve())
        except OSError:
            continue
    return found


def _read_dist_info_name(dist_info_dir: Path) -> Optional[str]:
    meta = dist_info_dir / "METADATA"
    if not meta.is_file():
        return None
    try:
        text = meta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("Name:"):
            return line.split(":", 1)[1].strip()
    return None


def _record_py_files(site_packages: Path, dist_info_dir: Path) -> Set[Path]:
    """Resolve .py paths listed in RECORD relative to site-packages."""
    record = dist_info_dir / "RECORD"
    out: Set[Path] = set()
    if not record.is_file():
        return out
    try:
        lines = record.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    site_resolved = site_packages.resolve()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        rel = line.split(",", 1)[0].strip()
        if not rel.endswith(".py"):
            continue
        # RECORD uses forward slashes
        rel_norm = rel.replace("\\", "/")
        abs_path = (site_packages / Path(rel_norm)).resolve()
        try:
            abs_path.relative_to(site_resolved)
        except ValueError:
            continue
        out.add(abs_path)
    return out


def build_allowlisted_site_packages_py_files(
    project_root: Path, distribution_names: Collection[str]
) -> FrozenSet[Path]:
    """
    Absolute paths of ``.py`` files belonging to allowlisted pip distributions.

    Resolution uses each ``*.dist-info`` directory: METADATA ``Name:`` must match
    (PEP 503–normalized) an entry in ``distribution_names``; file list comes from RECORD.

    If RECORD is missing or empty for a match, nothing is added for that distribution
    (no fallback guess by import name).
    """
    allow = {
        normalize_pep503_distribution_name(x)
        for x in distribution_names
        if x and str(x).strip()
    }
    if not allow:
        return frozenset()

    out: Set[Path] = set()
    for site_packages in iter_site_packages_dirs(project_root):
        try:
            entries = list(site_packages.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            name = entry.name
            if not name.endswith(".dist-info"):
                continue
            dname = _read_dist_info_name(entry)
            if dname is None:
                continue
            if normalize_pep503_distribution_name(dname) not in allow:
                continue
            out |= _record_py_files(site_packages, entry)

    return frozenset(out)


def iter_project_python_files_excluding_venv(project_root: Path) -> List[Path]:
    """
    Walk project tree for ``.py`` files, excluding hidden dirs and venv/data/logs.

    Mirrors :func:`code_analysis.commands.code_mapper_mcp_command` discovery
    (no ``.venv`` / ``venv`` traversal).
    """
    from .constants import DATA_DIR_NAME, DEFAULT_IGNORE_PATTERNS, LOGS_DIR_NAME

    ignore_dirs = DEFAULT_IGNORE_PATTERNS | {DATA_DIR_NAME, LOGS_DIR_NAME}
    root_path = project_root.resolve()
    files: List[Path] = []
    for walk_root, dirs, walk_files in os.walk(root_path):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in ignore_dirs
            and d not in (".venv", "venv")
        ]
        for f in walk_files:
            if f.endswith(".py"):
                files.append(Path(walk_root) / f)
    return files


def allowed_venv_py_files_for_watch_dir(watch_dir: Path) -> Set[Path]:
    """
    Union of allowlisted ``site-packages`` ``.py`` paths for all projects under ``watch_dir``.

    Used by file watcher scans that do not already have a discovered-project list.
    """
    allowlist = load_venv_site_packages_index_allowlist_from_config()
    if not allowlist:
        return set()
    try:
        from ..project_discovery import (
            DuplicateProjectIdError,
            NestedProjectError,
            discover_projects_in_directory,
        )

        discovered = discover_projects_in_directory(watch_dir)
    except (NestedProjectError, DuplicateProjectIdError, OSError, ValueError) as e:
        logger.debug("allowed_venv_py_files_for_watch_dir: %s", e)
        return set()
    except Exception as e:
        logger.debug("allowed_venv_py_files_for_watch_dir: %s", e)
        return set()
    out: Set[Path] = set()
    for proj in discovered:
        out.update(build_allowlisted_site_packages_py_files(proj.root_path, allowlist))
    return out


def collect_python_files_for_indexing(
    project_root: Path, distribution_allowlist: Collection[str]
) -> List[Path]:
    """
    Project sources (excluding venv) plus allowlisted site-packages ``.py`` files.

    Ordering: os.walk order for project files, then sorted allowlisted venv paths.
    """
    base = iter_project_python_files_excluding_venv(project_root)
    extra = build_allowlisted_site_packages_py_files(
        project_root, distribution_allowlist
    )
    merged: Set[Path] = set(base) | set(extra)
    return sorted(merged)


def format_project_venv_write_forbidden_message() -> str:
    return (
        "Writes under the project virtual environment (.venv or venv) are not allowed; "
        "that tree is read-only for server commands. Use project pip commands to "
        "change installed packages."
    )
