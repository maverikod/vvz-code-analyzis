"""
Indexed file set construction for paginated search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from code_analysis.core.search_session.file_sets.freshness import (
    DiskFileMetadata,
    FreshnessVerdict,
    IndexedFileRecord,
    validate_freshness,
)


@dataclass(frozen=True)
class IndexedFileSet:
    """Project files whose indexed state is fresh for current disk content."""

    files: frozenset[str]


def build_indexed_file_set(
    database_files: Mapping[str, IndexedFileRecord],
    disk_files: Iterable[str],
    disk_metadata: Mapping[str, DiskFileMetadata],
    *,
    draft_only_paths: Iterable[str] = (),
) -> IndexedFileSet:
    """
    Build the indexed file set from database and disk intersections.

    A file is included only when:
    - it appears in both ``database_files`` and ``disk_files``
    - it is not in ``draft_only_paths``
    - ``disk_metadata`` contains its path
    - ``validate_freshness`` returns FRESH

    Args:
        database_files: Indexed metadata keyed by project-relative path.
        disk_files: Project-relative paths present on disk.
        disk_metadata: On-disk checksum and mtime keyed by project-relative path.
        draft_only_paths: Paths that exist only as drafts; excluded even when fresh.

    Returns:
        IndexedFileSet containing only fresh intersection members.
    """
    draft_exclusions: frozenset[str] = frozenset(draft_only_paths)
    fresh_paths: set[str] = set()
    disk_path_set = set(disk_files)

    for file_path in disk_path_set:
        if file_path in draft_exclusions:
            continue
        record = database_files.get(file_path)
        if record is None:
            continue
        disk_meta = disk_metadata.get(file_path)
        if disk_meta is None:
            continue
        if validate_freshness(record, disk_meta) is FreshnessVerdict.FRESH:
            fresh_paths.add(file_path)

    return IndexedFileSet(files=frozenset(fresh_paths))
