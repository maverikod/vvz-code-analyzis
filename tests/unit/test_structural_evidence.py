"""Unit tests for structural evidence qualification."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.search_session.preview_reference import PreviewReference
from code_analysis.core.search_session.structural_evidence import (
    PhaseOutcome,
    qualify_structural_evidence,
)
from code_analysis.core.search_session.tree_representation import TreeRepresentationRef


def _tree_ref() -> TreeRepresentationRef:
    return TreeRepresentationRef(
        file_path="src/example.py",
        sidecar_path=Path("/tmp/example.tree"),
        content_checksum="a" * 64,
        root_stable_id="root-1",
    )


def _preview_ref() -> PreviewReference:
    return PreviewReference(
        file_path="src/example.py",
        node_id="node-1",
        selector=None,
        draft_session_id=None,
    )


def test_timed_out_rejected() -> None:
    verdict = qualify_structural_evidence(
        phase_outcome=PhaseOutcome.timed_out,
        tree_ref=_tree_ref(),
        preview_ref=_preview_ref(),
        source_mode="structural",
    )

    assert verdict.accepted is False
    assert verdict.reason_code == "REJECTED_PHASE_TIMED_OUT"
    assert verdict.preview_ref is None


def test_classic_line_without_preview_rejected() -> None:
    verdict = qualify_structural_evidence(
        phase_outcome=PhaseOutcome.completed,
        tree_ref=_tree_ref(),
        preview_ref=None,
        source_mode="classic_line",
    )

    assert verdict.accepted is False
    assert verdict.reason_code == "REJECTED_LINE_ONLY"
    assert verdict.preview_ref is None


def test_valid_structural_accepted() -> None:
    preview = _preview_ref()
    verdict = qualify_structural_evidence(
        phase_outcome=PhaseOutcome.completed,
        tree_ref=_tree_ref(),
        preview_ref=preview,
        source_mode="structural",
    )

    assert verdict.accepted is True
    assert verdict.reason_code == "ACCEPTED_STRUCTURAL"
    assert verdict.preview_ref is preview
