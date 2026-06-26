"""Tests for watch directory accessibility helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from code_analysis.core.watch_dir_access import describe_watch_dir_access
from code_analysis.main_workers_file_watcher import build_file_watcher_watch_dir_entries


def test_describe_watch_dir_access_missing(tmp_path: Path) -> None:
    """Verify test describe watch dir access missing."""
    missing = tmp_path / "does-not-exist"
    assert describe_watch_dir_access(missing) == "directory does not exist"


def test_describe_watch_dir_access_file_not_dir(tmp_path: Path) -> None:
    """Verify test describe watch dir access file not dir."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")
    assert describe_watch_dir_access(file_path) == "path is not a directory"


def test_describe_watch_dir_access_ok(tmp_path: Path) -> None:
    """Verify test describe watch dir access ok."""
    assert describe_watch_dir_access(tmp_path) is None


def test_build_file_watcher_watch_dir_entries_keeps_inaccessible(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify test build file watcher watch dir entries keeps inaccessible."""
    missing = tmp_path / "missing"
    config = [{"id": "wd-1", "path": str(missing)}]
    with caplog.at_level(logging.WARNING):
        entries = build_file_watcher_watch_dir_entries(config)

    assert len(entries) == 1
    assert entries[0]["id"] == "wd-1"
    assert entries[0]["path"] == str(missing.resolve())
    assert any("not accessible" in record.message for record in caplog.records)


def test_build_file_watcher_watch_dir_entries_preserves_ignore_patterns(
    tmp_path: Path,
) -> None:
    """Verify test build file watcher watch dir entries preserves ignore patterns."""
    config = [
        {
            "id": "wd-1",
            "path": str(tmp_path),
            "ignore_patterns": ["*.pyc"],
        }
    ]
    entries = build_file_watcher_watch_dir_entries(config)
    assert entries[0]["ignore_patterns"] == ["*.pyc"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read all dirs")
def test_describe_watch_dir_access_not_readable(tmp_path: Path) -> None:
    """Verify test describe watch dir access not readable."""
    unreadable = tmp_path / "secret"
    unreadable.mkdir()
    unreadable.chmod(0o000)
    try:
        issue = describe_watch_dir_access(unreadable)
        assert issue is not None
        assert "readable" in issue or "searchable" in issue
    finally:
        unreadable.chmod(0o700)
