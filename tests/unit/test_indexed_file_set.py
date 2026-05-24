"""Unit tests for indexed file set construction."""

from __future__ import annotations

from code_analysis.core.search_session.file_sets.freshness import (
    DiskFileMetadata,
    IndexedFileRecord,
)
from code_analysis.core.search_session.file_sets.indexed import build_indexed_file_set


def test_build_indexed_file_set_includes_only_fresh_intersection() -> None:
    database_files = {
        "src/fresh.py": IndexedFileRecord(
            file_path="src/fresh.py",
            indexed_checksum="same",
            indexed_mtime=10.0,
        ),
        "src/stale.py": IndexedFileRecord(
            file_path="src/stale.py",
            indexed_checksum="old",
            indexed_mtime=10.0,
        ),
        "src/missing_on_disk.py": IndexedFileRecord(
            file_path="src/missing_on_disk.py",
            indexed_checksum="same",
            indexed_mtime=10.0,
        ),
    }
    disk_files = ["src/fresh.py", "src/stale.py", "src/unindexed.py"]
    disk_metadata = {
        "src/fresh.py": DiskFileMetadata(checksum="same", mtime=10.0),
        "src/stale.py": DiskFileMetadata(checksum="new", mtime=10.0),
        "src/unindexed.py": DiskFileMetadata(checksum="x", mtime=1.0),
    }

    indexed = build_indexed_file_set(database_files, disk_files, disk_metadata)

    assert indexed.files == frozenset({"src/fresh.py"})


def test_build_indexed_file_set_excludes_stale_disk_file() -> None:
    database_files = {
        "README.md": IndexedFileRecord(
            file_path="README.md",
            indexed_checksum="v1",
            indexed_mtime=5.0,
        ),
    }
    disk_files = ["README.md"]
    disk_metadata = {
        "README.md": DiskFileMetadata(checksum="v1", mtime=6.0),
    }

    indexed = build_indexed_file_set(database_files, disk_files, disk_metadata)

    assert indexed.files == frozenset()
