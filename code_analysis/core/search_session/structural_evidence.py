"""
Structural evidence qualification for paginated search sessions.

Line grep is not structural evidence unless converted to a PreviewReference.
Timed-out or cancelled phases must not emit partial invalid evidence.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from code_analysis.core.search_session.preview_reference import PreviewReference
from code_analysis.core.search_session.tree_representation import TreeRepresentationRef


class PhaseOutcome(str, Enum):
    """Lifecycle outcome of a structural search phase."""

    completed = "completed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    running = "running"


@dataclass(frozen=True)
class StructuralEvidenceVerdict:
    """Qualification result for one structural evidence candidate."""

    accepted: bool
    reason_code: str
    preview_ref: Optional[PreviewReference]
REJECTED_PHASE_INCOMPLETE: str = "REJECTED_PHASE_INCOMPLETE"
REJECTED_PHASE_CANCELLED: str = "REJECTED_PHASE_CANCELLED"
REJECTED_PHASE_TIMED_OUT: str = "REJECTED_PHASE_TIMED_OUT"
REJECTED_LINE_ONLY: str = "REJECTED_LINE_ONLY"
REJECTED_MISSING_TREE: str = "REJECTED_MISSING_TREE"
REJECTED_MISSING_PREVIEW: str = "REJECTED_MISSING_PREVIEW"
ACCEPTED_STRUCTURAL: str = "ACCEPTED_STRUCTURAL"


def qualify_structural_evidence(
    *,
    phase_outcome: PhaseOutcome,
    tree_ref: Optional[TreeRepresentationRef],
    preview_ref: Optional[PreviewReference],
    source_mode: str,
) -> StructuralEvidenceVerdict:
    """
    Decide whether structural evidence may be emitted for a search phase.

    Decision order:
    - phase_outcome == running => reject REJECTED_PHASE_INCOMPLETE
    - phase_outcome == cancelled => reject REJECTED_PHASE_CANCELLED
    - phase_outcome == timed_out => reject REJECTED_PHASE_TIMED_OUT
    - source_mode == 'classic_line' and preview_ref is None => reject REJECTED_LINE_ONLY
    - tree_ref is None => reject REJECTED_MISSING_TREE
    - preview_ref is None => reject REJECTED_MISSING_PREVIEW
    - completed with both => accept ACCEPTED_STRUCTURAL
    """
    if phase_outcome is PhaseOutcome.running:
        return StructuralEvidenceVerdict(accepted=False, reason_code=REJECTED_PHASE_INCOMPLETE, preview_ref=None)
    if phase_outcome is PhaseOutcome.cancelled:
        return StructuralEvidenceVerdict(accepted=False, reason_code=REJECTED_PHASE_CANCELLED, preview_ref=None)
    if phase_outcome is PhaseOutcome.timed_out:
        return StructuralEvidenceVerdict(accepted=False, reason_code=REJECTED_PHASE_TIMED_OUT, preview_ref=None)
    if source_mode == "classic_line" and preview_ref is None:
        return StructuralEvidenceVerdict(accepted=False, reason_code=REJECTED_LINE_ONLY, preview_ref=None)
    if tree_ref is None:
        return StructuralEvidenceVerdict(accepted=False, reason_code=REJECTED_MISSING_TREE, preview_ref=None)
    if preview_ref is None:
        return StructuralEvidenceVerdict(accepted=False, reason_code=REJECTED_MISSING_PREVIEW, preview_ref=None)
    return StructuralEvidenceVerdict(accepted=True, reason_code=ACCEPTED_STRUCTURAL, preview_ref=preview_ref)


__all__ = [
    "PhaseOutcome",
    "StructuralEvidenceVerdict",
    "qualify_structural_evidence",
]
