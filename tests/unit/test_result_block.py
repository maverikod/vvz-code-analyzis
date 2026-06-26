"""Unit tests for SearchResultBlock assembly."""

from __future__ import annotations

import json

from code_analysis.core.search_session.result_block import (
    BLOCK_ITEMS_KEY,
    SearchResultBlock,
    assemble_block,
    block_items_from_payload,
    serialize_block,
)


def test_assemble_block_respects_size_limit_without_splitting() -> None:
    """Verify test assemble block respects size limit without splitting."""
    findings = [
        {"id": "1", "payload": "aa"},
        {"id": "2", "payload": "bb"},
        {"id": "3", "payload": "cc"},
    ]
    max_size = len(
        json.dumps({"position": 1, BLOCK_ITEMS_KEY: findings[:2]}).encode("utf-8")
    )

    block = assemble_block(findings, max_block_size_bytes=max_size, position=1)

    assert block.items == (findings[0], findings[1])
    assert block.position == 1
    assert block.serialized_size_bytes == len(serialize_block(block))


def test_oversized_single_result_forms_one_block_exceeding_limit() -> None:
    """Verify test oversized single result forms one block exceeding limit."""
    finding = {"id": "big", "payload": "x" * 500}
    max_size = 50

    block = assemble_block([finding], max_block_size_bytes=max_size, position=3)

    assert block.items == (finding,)
    assert block.serialized_size_bytes > max_size
    payload = json.loads(serialize_block(block))
    assert payload["position"] == 3
    assert payload[BLOCK_ITEMS_KEY] == [finding]


def test_serialize_block_round_trip_shape() -> None:
    """Verify test serialize block round trip shape."""
    block = SearchResultBlock(
        position=2,
        items=({"id": "x"},),
        serialized_size_bytes=0,
    )
    data = json.loads(serialize_block(block))
    assert data == {"position": 2, BLOCK_ITEMS_KEY: [{"id": "x"}]}


def test_block_items_from_payload_reads_legacy_results_key() -> None:
    """Verify test block items from payload reads legacy results key."""
    legacy = {"position": 1, "results": [{"result_id": "ft-000001"}]}
    assert block_items_from_payload(legacy) == [{"result_id": "ft-000001"}]
