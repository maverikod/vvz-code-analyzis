"""Unit tests for SearchResultBlock assembly."""

from __future__ import annotations

import json

from code_analysis.core.search_session.result_block import (
    SearchResultBlock,
    assemble_block,
    serialize_block,
)


def test_assemble_block_respects_size_limit_without_splitting() -> None:
    findings = [
        {"id": "1", "payload": "aa"},
        {"id": "2", "payload": "bb"},
        {"id": "3", "payload": "cc"},
    ]
    max_size = len(json.dumps({"position": 1, "results": findings[:2]}).encode("utf-8"))

    block = assemble_block(findings, max_block_size_bytes=max_size, position=1)

    assert block.results == (findings[0], findings[1])
    assert block.position == 1
    assert block.serialized_size_bytes == len(serialize_block(block))


def test_oversized_single_result_forms_one_block_exceeding_limit() -> None:
    finding = {"id": "big", "payload": "x" * 500}
    max_size = 50

    block = assemble_block([finding], max_block_size_bytes=max_size, position=3)

    assert block.results == (finding,)
    assert block.serialized_size_bytes > max_size
    payload = json.loads(serialize_block(block))
    assert payload["position"] == 3
    assert payload["results"] == [finding]


def test_serialize_block_round_trip_shape() -> None:
    block = SearchResultBlock(
        position=2,
        results=({"id": "x"},),
        serialized_size_bytes=0,
    )
    data = json.loads(serialize_block(block))
    assert data == {"position": 2, "results": [{"id": "x"}]}
