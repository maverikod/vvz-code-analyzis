"""
Unified search Finding entity and the shared scoring contract.

A Finding is the single homogeneous unit every search producer (database/cross,
grep, AST/XPath) reduces its raw result to. The block assembler then sorts and
segments a stream of Findings without knowing the source.

Address (identity): ``(file_path, stable_id)``. The selector / xpath / line
number a producer started from is only a *way to reach* a node; it always
resolves to that node's stable id inside the file, so it is NOT part of the
address. Representation (preview) is produced lazily from the address by the
existing preview mechanism and is never stored on the Finding.

Scoring is a shared concern, not a producer concern: relevance is computed the
same way as for database data. Each source reduces its raw signal to a single
``score`` via ``score_for_source`` (full-text rank, semantic similarity, exact
structural = 1.0, grep scored like database data).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

EXACT_STRUCTURAL_SCORE: float = 1.0


class FindingSource(str, Enum):
    """Producer that emitted a finding.

    The value is the access/method label; it does NOT determine the score
    (scoring is shared, see ``score_for_source``).
    """

    cross = "cross"
    fulltext = "fulltext"
    semantic = "semantic"
    grep = "grep"
    tree_query = "tree_query"


@dataclass(frozen=True)
class Finding:
    """One unified search result addressed by a node label inside a file.

    Attributes:
        result_id: Stable per-search identifier (e.g. ``cross-000123``). Used as
            the final, fully deterministic sort tie-break.
        source: Producer label (FindingSource value).
        file_path: Project-relative path of the file containing the node.
        stable_id: Stable node identifier inside the file (the address inside
            the file). Required: a finding without a node label is not a
            Finding (it stays a line-only hit upstream).
        score: Relevance in [0.0, 1.0], assigned by the shared scoring layer.
            Higher is more relevant.
        content_stale: True when the file's content was written through CA
            since its last successful reindex (bug 56c23bd9) - the result may
            not reflect the file's current on-disk content.
    """

    result_id: str
    source: str
    file_path: str
    stable_id: str
    score: float
    content_stale: bool = False

    def __post_init__(self) -> None:
        """Return post init."""
        if not self.file_path:
            raise ValueError("Finding.file_path must be non-empty")
        if not self.stable_id:
            raise ValueError("Finding.stable_id must be non-empty")

    @property
    def address(self) -> tuple[str, str]:
        """Return the ``(file_path, stable_id)`` address (identity of the node)."""
        return (self.file_path, self.stable_id)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for buffer persistence."""
        return {
            "result_id": self.result_id,
            "source": self.source,
            "file_path": self.file_path,
            "stable_id": self.stable_id,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        """Reconstruct a Finding from a persisted dict."""
        return cls(
            result_id=str(data["result_id"]),
            source=FindingSource(data["source"]),
            file_path=str(data["file_path"]),
            stable_id=str(data["stable_id"]),
            score=float(data["score"]),
        )


def serialize_finding(finding: Finding) -> bytes:
    """Serialize a Finding to UTF-8 JSON bytes."""
    return json.dumps(finding.to_dict(), ensure_ascii=False).encode("utf-8")


def _clamp_unit(value: float) -> float:
    """Clamp a score into the closed unit interval [0.0, 1.0]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def score_for_source(source: str, raw: dict[str, Any]) -> float:
    """Reduce a producer's raw signal to a single relevance score in [0, 1].

    This is the shared scoring contract: the score depends on the data, not on
    the access method. Mapping per source:

    - ``tree_query`` (AST/XPath): exact structural match -> ``1.0``.
    - ``semantic``: cosine ``similarity`` / ``score``.
    - ``fulltext``: normalized ``bm25`` / ``rank``.
    - ``cross``: pre-computed ``score`` from the cross orchestrator.
    - ``grep``: scored like database data (same ``score`` field when the
      cross/enrichment path supplied one); absent -> ``0.0``.

    Args:
        source: FindingSource value describing the producer.
        raw: The producer's raw result dict.

    Returns:
        Relevance score clamped to [0.0, 1.0].
    """
    if source == FindingSource.tree_query.value:
        return EXACT_STRUCTURAL_SCORE

    if source == FindingSource.semantic.value:
        value = raw.get("score")
        if value is None:
            value = raw.get("similarity")
        return _clamp_unit(float(value)) if value is not None else 0.0

    if source == FindingSource.fulltext.value:
        value = raw.get("bm25")
        if value is None:
            value = raw.get("rank")
        return _clamp_unit(float(value)) if value is not None else 0.0

    # cross and grep both carry a pre-computed ``score`` from the cross /
    # enrichment path; grep is scored the same way as database data.
    value = raw.get("score")
    return _clamp_unit(float(value)) if value is not None else 0.0
