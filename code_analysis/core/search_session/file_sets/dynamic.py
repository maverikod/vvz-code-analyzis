"""
Dynamic file set construction for paginated search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from code_analysis.core.search_session.file_sets.indexed import IndexedFileSet

DEFAULT_SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {".py", ".json", ".yaml", ".yml", ".md", ".txt"}
)
DEFAULT_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {"logs", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
)


@dataclass(frozen=True)
class DynamicFileSet:
    """Project files that must be processed directly from disk or draft session."""

    files: frozenset[str]


@dataclass
class BroadScanPolicy:
    """Opt-in policy for scanning beyond default supported formats."""

    enabled: bool = False
    include_logs: bool = False


def _path_has_excluded_dir(file_path: str, *, include_logs: bool) -> bool:
    """Return path has excluded dir."""
    parts = PurePosixPath(file_path).parts
    for part in parts[:-1]:
        if part == "logs":
            if not include_logs:
                return True
            continue
        if part in DEFAULT_EXCLUDED_DIR_NAMES:
            return True
    return False


def _path_has_supported_suffix(file_path: str) -> bool:
    """Return path has supported suffix."""
    return PurePosixPath(file_path).suffix in DEFAULT_SUPPORTED_SUFFIXES


def build_dynamic_file_set(
    disk_files: Iterable[str],
    indexed: IndexedFileSet,
    *,
    broad_scan: BroadScanPolicy = BroadScanPolicy(),
) -> DynamicFileSet:
    """
    Build the dynamic file set as disk files minus the fresh indexed set.

    Indexed members are always excluded. By default only supported suffixes are
    kept and paths under excluded directory names are skipped. When
    ``broad_scan.enabled`` is true the suffix allow-list is not applied. The
    ``logs`` directory is skipped unless ``broad_scan.include_logs`` is true.

    Args:
        disk_files: Project-relative paths present on disk.
        indexed: Fresh indexed file set to exclude from dynamic processing.
        broad_scan: Optional broad-scan policy overrides.

    Returns:
        DynamicFileSet of files requiring direct disk or draft processing.
    """
    dynamic_paths: set[str] = set()
    indexed_files = indexed.files

    for file_path in disk_files:
        if file_path in indexed_files:
            continue
        if _path_has_excluded_dir(
            file_path,
            include_logs=broad_scan.include_logs,
        ):
            continue
        if not broad_scan.enabled and not _path_has_supported_suffix(file_path):
            continue
        dynamic_paths.add(file_path)

    return DynamicFileSet(files=frozenset(dynamic_paths))
