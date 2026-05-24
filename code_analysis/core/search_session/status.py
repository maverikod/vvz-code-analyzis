"""
Search status and phase model for paginated search sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional

from code_analysis.core.search_session.manifest import SearchSessionManifest

STRUCTURAL_EVIDENCE_SUPPRESSED = "STRUCTURAL_EVIDENCE_SUPPRESSED"

_RUNNING_STATUS = "running"


class SearchPhase(str, Enum):
    """Current phase of search generation."""

    indexed_search = "indexed_search"
    dynamic_discovery = "dynamic_discovery"
    tree_validation = "tree_validation"
    tree_reconstruction = "tree_reconstruction"
    xpath_filtering = "xpath_filtering"
    block_writing = "block_writing"
    completion = "completion"


@dataclass(frozen=True)
class SearchStatusSnapshot:
    """Client-facing search status derived from session manifest."""

    status: str
    phase: SearchPhase
    block_not_ready: bool
    message: Optional[str]


def snapshot_from_manifest(manifest: SearchSessionManifest) -> SearchStatusSnapshot:
    """Build a status snapshot from persisted manifest fields."""
    phase = _phase_from_manifest(manifest.phase)
    block_not_ready = (
        manifest.status == _RUNNING_STATUS and manifest.block_ready_count == 0
    )
    return SearchStatusSnapshot(
        status=manifest.status,
        phase=phase,
        block_not_ready=block_not_ready,
        message=None,
    )


def apply_cancellation(
    snapshot: SearchStatusSnapshot,
    *,
    reason: str,
) -> SearchStatusSnapshot:
    """Return snapshot with cancelled status and the supplied reason."""
    return replace(
        snapshot,
        status="cancelled",
        block_not_ready=False,
        message=reason,
    )


def apply_timeout(
    snapshot: SearchStatusSnapshot,
    *,
    reason: str,
) -> SearchStatusSnapshot:
    """Return snapshot with timed_out status and structural evidence suppressed."""
    message = reason
    if STRUCTURAL_EVIDENCE_SUPPRESSED not in message:
        message = f"{reason}; {STRUCTURAL_EVIDENCE_SUPPRESSED}"
    return replace(
        snapshot,
        status="timed_out",
        block_not_ready=False,
        message=message,
    )


def _phase_from_manifest(raw_phase: str) -> SearchPhase:
    if not raw_phase:
        return SearchPhase.indexed_search
    try:
        return SearchPhase(raw_phase)
    except ValueError:
        return SearchPhase.indexed_search
