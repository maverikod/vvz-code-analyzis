"""
GrepSearchMode integration for structural preview references.

Maps fs_grep line matches to PreviewReference payloads after tree validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
from dataclasses import dataclass

from enum import Enum
from pathlib import Path
from typing import Any, cast

from code_analysis.core.search_session.preview_reference import (
    build_preview_reference,
    preview_reference_to_dict,
)
from code_analysis.core.search_session.tree_representation import (
    TreeRepresentationRef,
    validate_or_recreate_tree,
)


class GrepSearchMode(str, Enum):
    """Operating mode for paginated grep structural integration."""

    structural = "structural"
    classic_line = "classic_line"


DEFAULT_GREP_MODE = GrepSearchMode.structural
class StructuralEvidenceEligibility(str, Enum):
    """eligible when structural mode produced at least one preview_ref on a validated tree."""

    eligible = "eligible"
    ineligible = "ineligible"


@dataclass(frozen=True)
class GrepModeApplyResult:
    """Result of applying a grep mode to a set of line matches."""

    matches: list
    structural_evidence_eligibility: StructuralEvidenceEligibility


def _preview_ref_for_match(
    match: dict[str, Any],
    *,
    file_path: str,
    tree_ref: TreeRepresentationRef,
) -> dict[str, Any] | None:
    node_id = match.get("node_ref") or match.get("block_id")
    selector = match.get("selector")
    draft_session_id = match.get("session_id")

    if not node_id and not selector:
        return None

    stable_id_verified = bool(node_id)
    try:
        ref = build_preview_reference(
            file_path=file_path,
            node_id=str(node_id) if node_id else None,
            selector=str(selector) if selector else None,
            draft_session_id=str(draft_session_id) if draft_session_id else None,
            stable_id_verified=stable_id_verified,
        )
    except ValueError:
        return None
    return cast(dict[str, Any], preview_reference_to_dict(ref))


def enrich_line_matches_structural(
    *,
    project_root: Path,
    file_path: str,
    line_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate tree freshness and attach ``preview_ref`` to each match when possible."""
    if not line_matches:
        return line_matches

    try:
        tree_ref, _ = validate_or_recreate_tree(
            project_root=project_root,
            file_path=file_path,
        )
    except (NotImplementedError, FileNotFoundError, ValueError, OSError):
        return list(line_matches)

    enriched: list[dict[str, Any]] = []
    for match in line_matches:
        row = dict(match)
        preview_payload = _preview_ref_for_match(
            row,
            file_path=file_path,
            tree_ref=tree_ref,
        )
        if preview_payload is not None:
            row["preview_ref"] = preview_payload
        enriched.append(row)
    return enriched


def apply_grep_mode(
    *,
    mode: GrepSearchMode,
    project_root: Path,
    file_path: str,
    line_matches: list,
) -> GrepModeApplyResult:
    """classic_line returns matches unchanged ineligible; structural enriches and sets eligible when any preview_ref."""
    if mode == GrepSearchMode.classic_line:
        return GrepModeApplyResult(matches=list(line_matches), structural_evidence_eligibility=StructuralEvidenceEligibility.ineligible)
    enriched = enrich_line_matches_structural(project_root=project_root, file_path=file_path, line_matches=line_matches)
    eligibility = StructuralEvidenceEligibility.eligible if any(m.get("preview_ref") for m in enriched) else StructuralEvidenceEligibility.ineligible
    return GrepModeApplyResult(matches=enriched, structural_evidence_eligibility=eligibility)
def _group_matches_by_file(line_matches: list) -> dict:
    """Group matches by match['file_path']; raise ValueError when any match lacks file_path."""
    groups: dict = {}
    for m in line_matches:
        fp = m.get("file_path")
        if not fp:
            raise ValueError(f"match missing file_path: {m}")
        groups.setdefault(fp, []).append(m)
    return groups


def enrich_matches_per_file(*, project_root: Path, line_matches: list) -> list:
    """Group matches by file_path; call enrich_line_matches_structural once per distinct file."""
    groups = _group_matches_by_file(line_matches)
    result: list = []
    for fp, matches in groups.items():
        result.extend(enrich_line_matches_structural(project_root=project_root, file_path=fp, line_matches=matches))
    return result


def apply_grep_mode_multi_file(*, mode: GrepSearchMode, project_root: Path, line_matches: list) -> GrepModeApplyResult:
    """Paginated path entry — delegates to enrich_matches_per_file for structural; classic_line returns input unchanged."""
    if mode == GrepSearchMode.classic_line:
        return GrepModeApplyResult(matches=list(line_matches), structural_evidence_eligibility=StructuralEvidenceEligibility.ineligible)
    enriched = enrich_matches_per_file(project_root=project_root, line_matches=line_matches)
    eligibility = StructuralEvidenceEligibility.eligible if any(m.get("preview_ref") for m in enriched) else StructuralEvidenceEligibility.ineligible
    return GrepModeApplyResult(matches=enriched, structural_evidence_eligibility=eligibility)


__all__ = [
    "DEFAULT_GREP_MODE",
    "GrepSearchMode",
    "StructuralEvidenceEligibility",
    "GrepModeApplyResult",
    "apply_grep_mode",
    "apply_grep_mode_multi_file",
    "enrich_line_matches_structural",
    "enrich_matches_per_file",
]
