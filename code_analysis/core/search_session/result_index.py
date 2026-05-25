"""
Search result index for paginated search session blocks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from code_analysis.core.search_session.atomic_publication import atomic_write_json

COMPLETENESS_RUNNING = "search_still_running"
COMPLETENESS_FINISHED = "search_finished"


@dataclass
class SearchResultIndex:
    """
    Client-facing directory index listing published blocks and completeness state.

    The index carries two block sets that may differ in length:

    - Temporal set: blocks published in arrival order while the search runs.
      Exposed as ``temporal_blocks``; ``blocks`` is a backward-compatible alias
      that mirrors the same entries.
    - Relevance set: blocks re-segmented by descending relevance after the
      search finishes. Exposed as ``relevance_blocks``; empty until completion.

    Attributes:
        temporal_blocks: Ordered entries (``position``, ``size_bytes``) for the
            temporal block set published while the search runs.
        completeness: Running or finished completeness marker.
        reordered: True once the relevance set has been re-segmented and
            published after completion; False while the search runs.
        relevance_blocks: Ordered entries for the relevance-sorted block set;
            empty until ``reordered`` is True.
        blocks: Backward-compatible alias mirroring ``temporal_blocks``.
    """

    temporal_blocks: list[dict[str, Any]] = field(default_factory=list)
    completeness: str = COMPLETENESS_RUNNING
    reordered: bool = False
    relevance_blocks: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Keep blocks (legacy alias) and temporal_blocks in sync. Whichever was
        # provided non-empty wins; temporal_blocks is the canonical source.
        if self.temporal_blocks and not self.blocks:
            self.blocks = self.temporal_blocks
        elif self.blocks and not self.temporal_blocks:
            self.temporal_blocks = self.blocks
        else:
            self.blocks = self.temporal_blocks


def _index_to_dict(index: SearchResultIndex) -> dict[str, Any]:
    temporal = list(index.temporal_blocks)
    return {
        "temporal_blocks": temporal,
        "relevance_blocks": list(index.relevance_blocks),
        "reordered": bool(index.reordered),
        "completeness": index.completeness,
        # Backward-compatible alias: legacy readers expect a flat ``blocks`` key
        # mirroring the temporal set.
        "blocks": temporal,
    }


def _normalize_block_entries(raw: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        entries.append(
            {
                "position": int(entry["position"]),
                "size_bytes": int(entry["size_bytes"]),
            }
        )
    return entries


def _index_from_dict(data: dict[str, Any]) -> SearchResultIndex:
    # Canonical temporal source is ``temporal_blocks``; fall back to the legacy
    # flat ``blocks`` key for indexes written before dual-ordering.
    temporal_raw = data.get("temporal_blocks")
    if temporal_raw is None:
        temporal_raw = data.get("blocks")
    temporal_blocks = _normalize_block_entries(temporal_raw)
    relevance_blocks = _normalize_block_entries(data.get("relevance_blocks"))
    completeness = str(data.get("completeness") or COMPLETENESS_RUNNING)
    # Legacy indexes have no ``reordered`` flag; treat a populated relevance set
    # as already reordered for forward compatibility.
    reordered = bool(data.get("reordered", bool(relevance_blocks)))
    return SearchResultIndex(
        temporal_blocks=temporal_blocks,
        completeness=completeness,
        reordered=reordered,
        relevance_blocks=relevance_blocks,
    )


def read_index(index_path: Path) -> SearchResultIndex:
    """Load index JSON; raise FileNotFoundError when missing."""
    with open(index_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Index payload must be a JSON object: {index_path}")
    return _index_from_dict(data)


def append_block_entry(
    index_path: Path,
    *,
    position: int,
    size_bytes: int,
    completeness: str,
) -> SearchResultIndex:
    """Append one temporal block entry and atomically publish the updated index."""
    if index_path.is_file():
        current = read_index(index_path)
        temporal_blocks = list(current.temporal_blocks)
        relevance_blocks = list(current.relevance_blocks)
        reordered = current.reordered
    else:
        temporal_blocks = []
        relevance_blocks = []
        reordered = False

    temporal_blocks.append({"position": position, "size_bytes": size_bytes})
    updated = SearchResultIndex(
        temporal_blocks=temporal_blocks,
        completeness=completeness,
        reordered=reordered,
        relevance_blocks=relevance_blocks,
    )
    atomic_write_json(index_path, _index_to_dict(updated))
    return updated


def mark_index_finished(
    index_path: Path,
    *,
    relevance_blocks: list[dict[str, Any]] | None = None,
) -> SearchResultIndex:
    """
    Mark the index finished and attach the relevance-sorted block set.

    Preserves the existing temporal block entries, sets completeness to
    finished, marks the index as reordered, and records the relevance block
    entries produced by post-completion re-segmentation.

    Args:
        index_path: Path to the session index JSON.
        relevance_blocks: Entries (``position``, ``size_bytes``) for the
            relevance-sorted block set. None or empty leaves the relevance
            set empty and reordered False.

    Returns:
        The updated, atomically published SearchResultIndex.
    """
    current = read_index(index_path)
    relevance = _normalize_block_entries(relevance_blocks)
    updated = SearchResultIndex(
        temporal_blocks=list(current.temporal_blocks),
        completeness=COMPLETENESS_FINISHED,
        reordered=bool(relevance),
        relevance_blocks=relevance,
    )
    atomic_write_json(index_path, _index_to_dict(updated))
    return updated
