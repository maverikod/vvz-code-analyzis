"""
Stage S0 orchestrator: split project files into DB and grep working sets.

Gathers the inputs for the pure file_sets functions and returns the two
disjoint working sets used by the unified search:

- db_files: files whose indexed metadata is FRESH for current disk content
  (handled by the database/cross producer).
- grep_files: full disk list minus db_files (handled by the grep producer).

The split is a start-of-search snapshot; membership does not change mid-run.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from code_analysis.commands.project_fs_enumerate import enumerate_project_paths
from code_analysis.commands.file_management.relative_path_list_pattern import (
    canonical_relative_path,
)
from code_analysis.core.search_session.file_sets.dynamic import (
    BroadScanPolicy,
    build_dynamic_file_set,
)
from code_analysis.core.search_session.file_sets.freshness import (
    DiskFileMetadata,
    IndexedFileRecord,
)
from code_analysis.core.search_session.file_sets.indexed import (
    build_indexed_file_set,
)


class SupportsProjectFileRows(Protocol):
    """Minimal database client surface needed for the S0 split."""

    def get_project_file_rows(
        self, project_id: str, include_deleted: bool = False
    ) -> list[dict[str, Any]]:
        """Return file rows with RAW ``last_modified`` (Unix timestamp)."""
        ...


@dataclass(frozen=True)
class SearchFileSets:
    """Disjoint working sets produced by the S0 split.

    Attributes:
        db_files: Project-relative paths routed to the database/cross producer.
        grep_files: Project-relative paths routed to the grep producer.
    """

    db_files: frozenset[str]
    grep_files: frozenset[str]


def _collect_disk_paths(project_root: Path) -> dict[str, Path]:
    """Enumerate project files and map project-relative path -> absolute path.

    Uses the shared listing walk (skips venv / excluded dirs by default), the
    same enumeration backing ``list_project_files`` and ``fs_grep``.
    """
    root = project_root.resolve()
    relative_to_abs: dict[str, Path] = {}
    for abs_path in enumerate_project_paths(root, show_venv=False, python_only=False):
        relative = canonical_relative_path(root, abs_path)
        relative_to_abs[relative] = abs_path
    return relative_to_abs


def _build_disk_metadata(
    relative_to_abs: Mapping[str, Path],
) -> dict[str, DiskFileMetadata]:
    """Read on-disk mtime for each path.

    Checksum is left empty: routing at the ``files`` level compares mtime only
    (the table carries ``last_modified`` but no content checksum), and
    ``validate_freshness`` ignores ``checksum`` when the indexed record has no
    ``indexed_checksum``. Content checksums are a tree-validity concern handled
    later by ``validate_or_recreate_tree``.
    """
    disk_metadata: dict[str, DiskFileMetadata] = {}
    for relative, abs_path in relative_to_abs.items():
        try:
            mtime = os.stat(abs_path).st_mtime
        except OSError:
            continue
        disk_metadata[relative] = DiskFileMetadata(checksum="", mtime=mtime)
    return disk_metadata


def _build_database_files(
    database: SupportsProjectFileRows, project_id: str
) -> dict[str, IndexedFileRecord]:
    """Read indexed file rows and map project-relative path -> IndexedFileRecord.

    Uses ``get_project_file_rows`` (RAW ``last_modified`` as Unix timestamp).
    ``get_project_files`` must NOT be used here: it parses ``last_modified`` as
    a Julian date and breaks the mtime comparison, which would mark everything
    stale and dump the whole project into the grep set.
    """
    database_files: dict[str, IndexedFileRecord] = {}
    for row in database.get_project_file_rows(project_id, include_deleted=False):
        path = row.get("relative_path") or row.get("path")
        if not path:
            continue
        last_modified = row.get("last_modified")
        indexed_mtime = float(last_modified) if last_modified is not None else None
        database_files[str(path)] = IndexedFileRecord(
            file_path=str(path),
            indexed_checksum=None,
            indexed_mtime=indexed_mtime,
        )
    return database_files


def split_search_file_sets(
    *,
    project_root: Path,
    project_id: str,
    database: SupportsProjectFileRows,
    broad_scan: BroadScanPolicy = BroadScanPolicy(),
) -> SearchFileSets:
    """Build the DB and grep working sets for one search (start-of-run snapshot).

    Steps:
        1. Enumerate disk files under ``project_root`` (extension-mask walk).
        2. Read indexed file rows from the database (raw mtime).
        3. db_files = files FRESH for current disk content (intersection,
           ``validate_freshness``).
        4. grep_files = disk files minus db_files (suffix-filtered dynamic set).

    Args:
        project_root: Absolute project root directory.
        project_id: Project UUID.
        database: Client exposing ``get_project_file_rows``.
        broad_scan: Optional policy to widen the grep set beyond default suffixes.

    Returns:
        SearchFileSets with disjoint ``db_files`` and ``grep_files``.
    """
    relative_to_abs = _collect_disk_paths(project_root)
    disk_files = list(relative_to_abs.keys())
    disk_metadata = _build_disk_metadata(relative_to_abs)
    database_files = _build_database_files(database, project_id)

    indexed = build_indexed_file_set(
        database_files=database_files,
        disk_files=disk_files,
        disk_metadata=disk_metadata,
    )
    dynamic = build_dynamic_file_set(
        disk_files,
        indexed,
        broad_scan=broad_scan,
    )
    return SearchFileSets(
        db_files=indexed.files,
        grep_files=dynamic.files,
    )
