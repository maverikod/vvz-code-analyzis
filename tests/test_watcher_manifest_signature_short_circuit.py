"""
Unit tests for ``compute_project_files_signature`` and ``manifest_rebuild_needed``.

Verifies that disk signature computation correctly extracts file count, max mtime,
and total size for a project, and that the rebuild-needed check correctly
determines when to re-scan.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.file_watcher_pkg.watcher_disk_manifest import (
    compute_project_files_signature, manifest_rebuild_needed)


def test_compute_signature_single_project() -> None:
    """Compute signature for a single project filters correctly."""
    project_files = {
        "/path/to/file1.py": {
            "project_id": "p1",
            "mtime": 1000.5,
            "size": 100,
        },
        "/path/to/file2.py": {
            "project_id": "p1",
            "mtime": 1001.5,
            "size": 200,
        },
    }
    file_count, max_mtime, total_size = compute_project_files_signature(
        project_files, "p1"
    )
    assert file_count == 2
    assert max_mtime == 1001.5
    assert total_size == 300


def test_compute_signature_filters_other_projects() -> None:
    """Signature computation filters out files from other projects."""
    project_files = {
        "/path/to/file1.py": {
            "project_id": "p1",
            "mtime": 1000.5,
            "size": 100,
        },
        "/path/to/file2.py": {
            "project_id": "p2",
            "mtime": 2000.5,
            "size": 200,
        },
        "/path/to/file3.py": {
            "project_id": "p1",
            "mtime": 1002.5,
            "size": 50,
        },
    }
    file_count, max_mtime, total_size = compute_project_files_signature(
        project_files, "p1"
    )
    assert file_count == 2
    assert max_mtime == 1002.5
    assert total_size == 150


def test_compute_signature_includes_entries_without_project_id_key() -> None:
    """Entries without project_id key or with None are still counted (like build_project_disk_manifest)."""
    from typing import Any, Dict

    project_files: Dict[str, Dict[str, Any]] = {
        "/path/to/file1.py": {
            "project_id": "p1",
            "mtime": 1000.5,
            "size": 100,
        },
        "/path/to/file2.py": {
            # No project_id key at all
            "mtime": 1001.5,
            "size": 200,
        },
        "/path/to/file3.py": {
            "project_id": None,
            "mtime": 1002.5,
            "size": 50,
        },
    }
    file_count, max_mtime, total_size = compute_project_files_signature(
        project_files, "p1"
    )
    # Should count all three: file1 (p1), file2 (no key), file3 (None).
    # Only entries with a truthy different project_id are filtered out.
    assert file_count == 3
    assert max_mtime == 1002.5
    assert total_size == 350


def test_manifest_rebuild_needed_no_cache() -> None:
    """manifest_rebuild_needed returns True when cache is None."""
    result = manifest_rebuild_needed(
        "p1",
        (10, 1000.5, 5000),
        None,
    )
    assert result is True


def test_manifest_rebuild_needed_empty_cache() -> None:
    """manifest_rebuild_needed returns True when project not in cache."""
    cache: dict = {}
    result = manifest_rebuild_needed(
        "p1",
        (10, 1000.5, 5000),
        cache,
    )
    assert result is True


def test_manifest_rebuild_needed_matching_cache() -> None:
    """manifest_rebuild_needed returns False when signature matches cache."""
    signature = (10, 1000.5, 5000)
    cache = {"p1": signature}
    result = manifest_rebuild_needed(
        "p1",
        signature,
        cache,
    )
    assert result is False


def test_manifest_rebuild_needed_different_file_count() -> None:
    """manifest_rebuild_needed returns True when file count changes."""
    cache = {"p1": (10, 1000.5, 5000)}
    result = manifest_rebuild_needed(
        "p1",
        (11, 1000.5, 5000),  # Different file count
        cache,
    )
    assert result is True


def test_manifest_rebuild_needed_different_mtime() -> None:
    """manifest_rebuild_needed returns True when max mtime changes."""
    cache = {"p1": (10, 1000.5, 5000)}
    result = manifest_rebuild_needed(
        "p1",
        (10, 1001.5, 5000),  # Different mtime
        cache,
    )
    assert result is True


def test_manifest_rebuild_needed_different_size() -> None:
    """manifest_rebuild_needed returns True when total size changes."""
    cache = {"p1": (10, 1000.5, 5000)}
    result = manifest_rebuild_needed(
        "p1",
        (10, 1000.5, 5001),  # Different size
        cache,
    )
    assert result is True
