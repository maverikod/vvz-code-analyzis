"""Tests for shared listing-path glob helpers."""

from __future__ import annotations

from pathlib import Path

from code_analysis.commands.file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)


def test_effective_listing_pattern_prefers_file_pattern() -> None:
    assert effective_listing_pattern("*.py", "*.md") == "*.py"


def test_effective_listing_pattern_falls_back_to_glob() -> None:
    assert effective_listing_pattern(None, "*.md") == "*.md"
    assert effective_listing_pattern("", "x") == "x"


def test_canonical_relative_path_under_root(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    f = root / "a" / "b.txt"
    f.parent.mkdir()
    f.write_text("x")
    assert canonical_relative_path(root, f) == "a/b.txt"


def test_relative_path_matches_listing_fnmatch() -> None:
    assert relative_path_matches_listing_pattern("src/x.py", "*.py")


def test_literal_prefix_directory_with_trailing_slash() -> None:
    """``dir/`` must match the same paths as ``dir`` (no ``dir//`` prefix bug)."""
    assert relative_path_matches_listing_pattern(
        "code_analysis/commands/list_files.py", "code_analysis/commands/"
    )
    assert relative_path_matches_listing_pattern(
        "code_analysis/commands/list_files.py", "code_analysis/commands"
    )
    assert not relative_path_matches_listing_pattern(
        "code_analysis/commander/x.py", "code_analysis/commands/"
    )


def test_log_style_absolute_path_still_matches_fnmatch() -> None:
    p = "/var/log/app/file_watcher.log"
    assert relative_path_matches_listing_pattern(p, "*file_watcher*")
