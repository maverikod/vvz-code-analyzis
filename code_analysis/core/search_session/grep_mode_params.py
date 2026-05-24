"""
GrepSearchMode parameter mapping for fs_ggrep command dispatch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_analysis.commands.fs_grep_structural_integration import (
    DEFAULT_GREP_MODE,
    GrepModeApplyResult,
    GrepSearchMode,
    StructuralEvidenceEligibility,
    apply_ggrep_mode,
    apply_ggrep_mode_multi_file,
)

__all__ = [
    "DEFAULT_GREP_MODE",
    "FsGgrepModeParams",
    "GrepModeApplyResult",
    "GrepSearchMode",
    "StructuralEvidenceEligibility",
    "apply_ggrep_mode_multi_file_payload",
    "apply_ggrep_mode_to_match_payload",
    "grep_mode_to_fs_ggrep_params",
]


@dataclass(frozen=True)
class FsGgrepModeParams:
    """fs_ggrep flags derived from GrepSearchMode."""

    fast_text_only: bool
    enrich_blocks: bool


def grep_mode_to_fs_ggrep_params(mode: GrepSearchMode) -> FsGgrepModeParams:
    """Map GrepSearchMode to existing fs_ggrep fast_text_only / enrich_blocks flags."""
    if mode == GrepSearchMode.structural:
        return FsGgrepModeParams(fast_text_only=False, enrich_blocks=True)
    return FsGgrepModeParams(fast_text_only=True, enrich_blocks=False)


def apply_ggrep_mode_to_match_payload(
    *,
    mode: GrepSearchMode,
    project_root: Path,
    file_path: str,
    line_matches: list[dict[str, Any]],
) -> GrepModeApplyResult:
    """Apply grep mode enrichment to a single-file match payload."""
    return apply_ggrep_mode(
        mode=mode,
        project_root=project_root,
        file_path=file_path,
        line_matches=line_matches,
    )


def apply_ggrep_mode_multi_file_payload(
    *,
    mode: GrepSearchMode,
    project_root: Path,
    line_matches: list[dict[str, Any]],
) -> GrepModeApplyResult:
    """Apply grep mode enrichment for paginated multi-file match batches."""
    return apply_ggrep_mode_multi_file(
        mode=mode,
        project_root=project_root,
        line_matches=line_matches,
    )
