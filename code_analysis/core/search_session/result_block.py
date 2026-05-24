"""
Search result block assembly and serialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchResultBlock:
    """
    Immutable published slice of search results.

    Attributes:
        position: Block position number in the session index.
        results: Complete search results contained in this block.
        serialized_size_bytes: UTF-8 JSON size of the serialized block payload.
    """

    position: int
    results: tuple[dict[str, Any], ...]
    serialized_size_bytes: int


def _block_payload(block: SearchResultBlock) -> dict[str, Any]:
    return {
        "position": block.position,
        "results": list(block.results),
    }


def serialize_block(block: SearchResultBlock) -> bytes:
    """Serialize a block to UTF-8 JSON bytes."""
    return json.dumps(_block_payload(block), ensure_ascii=False).encode("utf-8")


def _assembled_size_bytes(results: list[dict[str, Any]]) -> int:
    payload = {"position": 0, "results": results}
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def assemble_block(
    findings: list[dict[str, Any]],
    *,
    max_block_size_bytes: int,
    position: int,
) -> SearchResultBlock:
    """
    Pack whole findings into one block without splitting a single result.

    Stops before adding a finding that would exceed ``max_block_size_bytes`` unless
    the block is still empty and that finding alone exceeds the limit.
    """
    selected: list[dict[str, Any]] = []
    for finding in findings:
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
        results=tuple(selected),
        serialized_size_bytes=0,
    )
    size = len(serialize_block(block))
    return SearchResultBlock(
        position=position,
        results=block.results,
        serialized_size_bytes=size,
    )
