"""Unit tests for search freshness validation."""

from __future__ import annotations

from code_analysis.core.search_session.file_sets.freshness import (
    DiskFileMetadata,
    FreshnessVerdict,
    IndexedFileRecord,
    validate_freshness,
)


def test_validate_freshness_returns_fresh_when_checksum_and_mtime_match() -> None:
    """Verify test validate freshness returns fresh when checksum and mtime match."""
    record = IndexedFileRecord(
        file_path="src/app.py",
        indexed_checksum="abc123",
        indexed_mtime=100.0,
    )
    disk = DiskFileMetadata(checksum="abc123", mtime=100.0)

    assert validate_freshness(record, disk) is FreshnessVerdict.FRESH


def test_validate_freshness_returns_stale_on_checksum_mismatch() -> None:
    """Verify test validate freshness returns stale on checksum mismatch."""
    record = IndexedFileRecord(
        file_path="src/app.py",
        indexed_checksum="abc123",
        indexed_mtime=100.0,
    )
    disk = DiskFileMetadata(checksum="def456", mtime=100.0)

    assert validate_freshness(record, disk) is FreshnessVerdict.STALE


def test_validate_freshness_returns_stale_when_disk_mtime_is_newer() -> None:
    """Verify test validate freshness returns stale when disk mtime is newer."""
    record = IndexedFileRecord(
        file_path="src/app.py",
        indexed_checksum="abc123",
        indexed_mtime=100.0,
    )
    disk = DiskFileMetadata(checksum="abc123", mtime=101.0)

    assert validate_freshness(record, disk) is FreshnessVerdict.STALE


def test_validate_freshness_returns_missing_index_when_record_is_none() -> None:
    """Verify test validate freshness returns missing index when record is none."""
    disk = DiskFileMetadata(checksum="abc123", mtime=100.0)

    assert validate_freshness(None, disk) is FreshnessVerdict.MISSING_INDEX


def test_validate_freshness_returns_unavailable_index_without_metadata() -> None:
    """Verify test validate freshness returns unavailable index without metadata."""
    record = IndexedFileRecord(
        file_path="src/app.py",
        indexed_checksum=None,
        indexed_mtime=None,
    )
    disk = DiskFileMetadata(checksum="abc123", mtime=100.0)

    assert validate_freshness(record, disk) is FreshnessVerdict.UNAVAILABLE_INDEX
