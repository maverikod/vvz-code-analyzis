"""Unit tests for GrepSearchMode fs_ggrep parameter mapping."""

from __future__ import annotations

from pathlib import Path

from code_analysis.commands.fs_grep_structural_integration import (
    DEFAULT_GREP_MODE,
    GrepSearchMode,
)
from code_analysis.core.search_session.grep_mode_params import (
    FsGgrepModeParams,
    apply_grep_mode_to_match_payload,
    grep_mode_to_fs_ggrep_params,
)


def test_grep_mode_to_fs_ggrep_params_structural() -> None:
    """Verify test grep mode to fs ggrep params structural."""
    params = grep_mode_to_fs_ggrep_params(GrepSearchMode.structural)

    assert params == FsGgrepModeParams(fast_text_only=False, enrich_blocks=True)


def test_grep_mode_to_fs_ggrep_params_classic_line() -> None:
    """Verify test grep mode to fs ggrep params classic line."""
    params = grep_mode_to_fs_ggrep_params(GrepSearchMode.classic_line)

    assert params == FsGgrepModeParams(fast_text_only=True, enrich_blocks=False)


def test_default_grep_mode_reexported() -> None:
    """Verify test default grep mode reexported."""
    assert DEFAULT_GREP_MODE == GrepSearchMode.structural


def test_apply_grep_mode_to_match_payload_classic_line_unchanged() -> None:
    """Verify test apply grep mode to match payload classic line unchanged."""
    matches = [{"line_number": 1, "line": "text"}]

    result = apply_grep_mode_to_match_payload(
        mode=GrepSearchMode.classic_line,
        project_root=Path("/tmp/unused"),
        file_path="a.py",
        line_matches=matches,
    )

    assert result.matches == matches
    assert result.structural_evidence_eligibility.value == "ineligible"
