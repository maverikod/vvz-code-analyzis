"""
Search result index for paginated search session blocks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_analysis.core.search_session.atomic_publication import atomic_write_json

COMPLETENESS_RUNNING = "search_still_running"
COMPLETENESS_FINISHED = "search_finished"


@dataclass
class SearchResultIndex:
    """
    Client-facing directory index listing published blocks and completeness state.

    Attributes:
        blocks: Ordered entries with ``position`` and ``size_bytes`` per block.
        completeness: Running or finished completeness marker.
    """

    blocks: list[dict[str, Any]]
    completeness: str


def _index_to_dict(index: SearchResultIndex) -> dict[str, Any]:
    return {"blocks": list(index.blocks), "completeness": index.completeness}


def _index_from_dict(data: dict[str, Any]) -> SearchResultIndex:
    blocks_raw = data.get("blocks") or []
    blocks: list[dict[str, Any]] = []
    for entry in blocks_raw:
        if not isinstance(entry, dict):
            continue
        blocks.append(
            {
                "position": int(entry["position"]),
                "size_bytes": int(entry["size_bytes"]),
            }
        )
    completeness = str(data.get("completeness") or COMPLETENESS_RUNNING)
    return SearchResultIndex(blocks=blocks, completeness=completeness)


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
    """Append one block entry and atomically publish the updated index."""
    if index_path.is_file():
        current = read_index(index_path)
        blocks = list(current.blocks)
    else:
        blocks = []

    blocks.append({"position": position, "size_bytes": size_bytes})
    updated = SearchResultIndex(blocks=blocks, completeness=completeness)
    atomic_write_json(index_path, _index_to_dict(updated))
    return updated


def mark_index_finished(index_path: Path) -> SearchResultIndex:
    """Set completeness to finished while preserving existing block entries."""
    current = read_index(index_path)
    updated = SearchResultIndex(
        blocks=list(current.blocks),
        completeness=COMPLETENESS_FINISHED,
    )
    atomic_write_json(index_path, _index_to_dict(updated))
    return updated
