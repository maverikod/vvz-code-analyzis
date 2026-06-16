"""
Search result block assembly and serialization.

On-disk and API blocks share one shape::

    {"position": <int>, "items": [<finding>, ...]}

Each *finding* is a flat JSON object (see ``Finding`` in ``finding.py`` plus
optional preview fields such as ``text`` / ``line``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

BLOCK_ITEMS_KEY = "items"
LEGACY_BLOCK_RESULTS_KEY = "results"


@dataclass(frozen=True)
class SearchResultBlock:
    """
    Immutable published slice of search results.

    Attributes:
        position: Block position number in the session index.
        items: Complete search findings contained in this block.
        serialized_size_bytes: UTF-8 JSON size of the serialized block payload.
    """

    position: int
    items: tuple[dict[str, Any], ...]
    serialized_size_bytes: int


def block_items_from_payload(payload: dict[str, Any] | list) -> list[dict[str, Any]]:
    """Extract findings from a block JSON payload (current or legacy key)."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    raw = payload.get(BLOCK_ITEMS_KEY)
    if raw is None:
        raw = payload.get(LEGACY_BLOCK_RESULTS_KEY)
    if raw is None:
        raw = payload.get("matches")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _block_payload(block: SearchResultBlock) -> dict[str, Any]:
    return {
        "position": block.position,
        BLOCK_ITEMS_KEY: list(block.items),
    }


def serialize_block(block: SearchResultBlock) -> bytes:
    """Serialize a block to UTF-8 JSON bytes."""
    return json.dumps(_block_payload(block), ensure_ascii=False).encode("utf-8")


def _assembled_size_bytes(items: list[dict[str, Any]]) -> int:
    payload = {"position": 0, BLOCK_ITEMS_KEY: items}
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def assemble_block(
    findings: list[dict[str, Any]],
    *,
    max_block_size_bytes: int,
    position: int,
    max_results: int | None = None,
) -> SearchResultBlock:
    """
    Pack whole findings into one block without splitting a single result.

    Stops before adding a finding that would exceed ``max_block_size_bytes`` unless
    the block is still empty and that finding alone exceeds the limit. When
    ``max_results`` is set, also caps the number of findings per block.
    """
    selected: list[dict[str, Any]] = []
    for finding in findings:
        if max_results is not None and len(selected) >= max_results:
            break
        if not selected:
            selected.append(finding)
            if _assembled_size_bytes(selected) > max_block_size_bytes:
                break
            continue

        candidate = selected + [finding]
        if _assembled_size_bytes(candidate) > max_block_size_bytes:
            break
        selected.append(finding)

    block = SearchResultBlock(
        position=position,
        items=tuple(selected),
        serialized_size_bytes=0,
    )
    size = len(serialize_block(block))
    return SearchResultBlock(
        position=position,
        items=block.items,
        serialized_size_bytes=size,
    )
