"""Tests for per-watch-dir settings helpers."""

from __future__ import annotations

import json
from pathlib import Path

from code_analysis.core.watch_dir_settings import (
    DEFAULT_WATCH_DIR_IGNORE_PATTERNS,
    load_watch_dir_settings,
    merge_watch_ignore_patterns,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGING_EXAMPLE_SETTINGS = (
    _REPO_ROOT
    / "packaging/watch-catalog-example/550e8400-e29b-41d4-a716-446655440001/settings.json"
)


def test_merge_watch_ignore_patterns_deduplicates_and_preserves_order() -> None:
    merged = merge_watch_ignore_patterns(
        ["**/.venv/**", "**/custom/**"],
        ["**/.venv/**", "**/__pycache__/**"],
    )
    assert merged == ("**/.venv/**", "**/custom/**", "**/__pycache__/**")


def test_merge_watch_ignore_patterns_skips_blank_entries() -> None:
    merged = merge_watch_ignore_patterns(["", "  "], ["**/.cache/**"])
    assert merged == ("**/.cache/**",)


def test_packaging_watch_catalog_example_settings_match_defaults() -> None:
    assert _PACKAGING_EXAMPLE_SETTINGS.is_file()
    watch_dir = _PACKAGING_EXAMPLE_SETTINGS.parent
    settings = load_watch_dir_settings(watch_dir)
    assert settings.deleted is False
    assert list(settings.ignore_patterns) == DEFAULT_WATCH_DIR_IGNORE_PATTERNS
    raw = json.loads(_PACKAGING_EXAMPLE_SETTINGS.read_text(encoding="utf-8"))
    assert raw["ignore_patterns"] == DEFAULT_WATCH_DIR_IGNORE_PATTERNS
