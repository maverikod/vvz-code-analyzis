"""Tests for watch dir id normalization in initialize_watch_dirs."""

from __future__ import annotations

from uuid import UUID

from code_analysis.core.file_watcher_pkg.multi_project_worker_init import (
    _watch_dir_id_str,
)


def test_watch_dir_id_str_normalizes_uuid_to_same_string_as_config() -> None:
    u = UUID("550e8400-e29b-41d4-a716-446655440000")
    s = "550e8400-e29b-41d4-a716-446655440000"
    assert _watch_dir_id_str(u) == _watch_dir_id_str(s)
    assert _watch_dir_id_str(s) in {s}
    assert _watch_dir_id_str(u) in {s}


def test_watch_dir_id_str_empty_for_none() -> None:
    assert _watch_dir_id_str(None) == ""
