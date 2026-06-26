"""Unit tests for dynamic file set construction."""

from __future__ import annotations

from code_analysis.core.search_session.file_sets.dynamic import (
    BroadScanPolicy,
    build_dynamic_file_set,
)
from code_analysis.core.search_session.file_sets.indexed import IndexedFileSet


def test_build_dynamic_file_set_excludes_indexed_members() -> None:
    """Verify test build dynamic file set excludes indexed members."""
    indexed = IndexedFileSet(files=frozenset({"src/indexed.py"}))
    disk_files = ["src/indexed.py", "src/dynamic.py"]

    dynamic = build_dynamic_file_set(disk_files, indexed)

    assert dynamic.files == frozenset({"src/dynamic.py"})


def test_build_dynamic_file_set_excludes_log_files_by_default() -> None:
    """Verify test build dynamic file set excludes log files by default."""
    indexed = IndexedFileSet(files=frozenset())
    disk_files = ["logs/app.log", "src/app.py"]

    dynamic = build_dynamic_file_set(disk_files, indexed)

    assert "logs/app.log" not in dynamic.files
    assert "src/app.py" in dynamic.files


def test_build_dynamic_file_set_includes_logs_with_broad_scan_policy() -> None:
    """Verify test build dynamic file set includes logs with broad scan policy."""
    indexed = IndexedFileSet(files=frozenset())
    disk_files = ["logs/app.log", "src/app.py"]
    broad_scan = BroadScanPolicy(enabled=True, include_logs=True)

    dynamic = build_dynamic_file_set(disk_files, indexed, broad_scan=broad_scan)

    assert dynamic.files == frozenset({"logs/app.log", "src/app.py"})
