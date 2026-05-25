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
from dataclasses import dataclass
from typing import Iterable, Mapping
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


@dataclass(frozen=True)
class SearchFileSets:
    """Disjoint working sets produced by the S0 split.

    Attributes:
        db_files: Project-relative paths routed to the database/cross producer.
        grep_files: Project-relative paths routed to the grep producer.
    """

    db_files: frozenset[str]
    grep_files: frozenset[str]


def split_search_file_sets(
    *,
    disk_files: Iterable[str],
    disk_metadata: Mapping[str, DiskFileMetadata],
    database_files: Mapping[str, IndexedFileRecord],
    broad_scan: BroadScanPolicy = BroadScanPolicy(),
) -> SearchFileSets:
    """Split the project file list into disjoint DB and grep working sets.

    Pure function: all inputs are pre-gathered by the caller (filesystem walk
    and database read live in the command/service layer, not in core). This
    keeps the file_sets package free of any dependency on the command layer.

    Routing:
        - db_files: paths FRESH for current disk content
          (``build_indexed_file_set`` -> ``validate_freshness``).
        - grep_files: disk files minus db_files, suffix-filtered
          (``build_dynamic_file_set``). Disjoint from db_files by construction,
          so findings need no cross-set dedup.

    Membership is a start-of-search snapshot; the caller passes a fixed
    ``disk_files`` list for the whole run.

    Args:
        disk_files: Project-relative paths present on disk (extension-mask walk).
        disk_metadata: On-disk mtime (and optional checksum) per path. Checksum
            may be empty: ``files``-level routing compares mtime only, and
            ``validate_freshness`` ignores checksum when the indexed record has
            no ``indexed_checksum``.
        database_files: Indexed metadata per path, built from
            ``get_project_file_rows`` (RAW ``last_modified`` as Unix timestamp).
            ``get_project_files`` must NOT be used to build this: it parses
            ``last_modified`` as a Julian date and would mark everything stale.
        broad_scan: Optional policy to widen the grep set beyond default
            supported suffixes.

    Returns:
        SearchFileSets with disjoint ``db_files`` and ``grep_files``.
    """
    disk_file_list = list(disk_files)
    indexed = build_indexed_file_set(
        database_files=database_files,
        disk_files=disk_file_list,
        disk_metadata=disk_metadata,
    )
    dynamic = build_dynamic_file_set(
        disk_file_list,
        indexed,
        broad_scan=broad_scan,
    )
    return SearchFileSets(
        db_files=indexed.files,
        grep_files=dynamic.files,
    )
