"""
Freshness validation for indexed file representations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FreshnessVerdict(str, Enum):
    """Outcome of comparing indexed metadata against on-disk content."""

    FRESH = "fresh"
    STALE = "stale"
    MISSING_INDEX = "missing_index"
    UNAVAILABLE_INDEX = "unavailable_index"


@dataclass(frozen=True)
class IndexedFileRecord:
    """Indexed file metadata known to the database or search index."""

    file_path: str
    indexed_checksum: Optional[str]
    indexed_mtime: Optional[float]


@dataclass(frozen=True)
class DiskFileMetadata:
    """Current checksum and modification metadata read from disk."""

    checksum: str
    mtime: float


def validate_freshness(
    record: Optional[IndexedFileRecord],
    disk: DiskFileMetadata,
) -> FreshnessVerdict:
    """
    Decide whether indexed metadata still matches on-disk content.

    Args:
        record: Database or index metadata for the file, if any.
        disk: Current on-disk checksum and modification time.

    Returns:
        FreshnessVerdict describing whether the indexed path may be used.
    """
    if record is None:
        return FreshnessVerdict.MISSING_INDEX

    has_checksum = record.indexed_checksum is not None
    has_mtime = record.indexed_mtime is not None
    if not has_checksum and not has_mtime:
        return FreshnessVerdict.UNAVAILABLE_INDEX

    indexed_checksum = record.indexed_checksum
    if has_checksum and indexed_checksum != disk.checksum:
        return FreshnessVerdict.STALE

    indexed_mtime = record.indexed_mtime
    if has_mtime and indexed_mtime is not None and disk.mtime > indexed_mtime:
        return FreshnessVerdict.STALE

    return FreshnessVerdict.FRESH
def is_stale_for_dynamic_routing(verdict: FreshnessVerdict) -> bool:
    """
    Return True when verdict is not FRESH.

    Non-FRESH verdicts emit the stale routing signal: files leave the indexed
    set and enter dynamic processing.
    """
    return verdict is not FreshnessVerdict.FRESH
