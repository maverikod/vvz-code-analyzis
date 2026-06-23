"""
Tests for get_code_entity_info response contract: file_path and cst_node_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid

import pytest

from code_analysis.commands.ast.entity_info import _is_valid_uuid4, _normalize_entities


def test_is_valid_uuid4_accepts_valid() -> None:
    """Valid UUID4 string is accepted."""
    valid = str(uuid.uuid4())
    assert _is_valid_uuid4(valid) is True


def test_is_valid_uuid4_rejects_none() -> None:
    """None is rejected."""
    assert _is_valid_uuid4(None) is False


def test_is_valid_uuid4_rejects_empty() -> None:
    """Empty or whitespace-only string is rejected."""
    assert _is_valid_uuid4("") is False
    assert _is_valid_uuid4("   ") is False


def test_is_valid_uuid4_rejects_invalid() -> None:
    """Non-UUID4 or invalid string is rejected."""
    assert _is_valid_uuid4("not-a-uuid") is False
    # UUID with version 1 (first digit of third group is 1) is not UUID4
    assert _is_valid_uuid4("550e8400-e29b-11d4-a716-446655440000") is False
    assert _is_valid_uuid4("0" * 36) is False


def test_normalize_entities_keeps_rows_regardless_of_cst_node_id() -> None:
    """All rows with a file_path are kept; cst_node_id is normalized to a valid
    UUID4 or None (a missing/invalid cst_node_id no longer drops the entity —
    TZ-CA-INDEX-INTEGRITY-001). Rows without a file_path are still excluded."""
    valid_id = str(uuid.uuid4())
    rows = [
        {"id": 1, "name": "Foo", "file_path": "src/foo.py", "line": 10, "cst_node_id": valid_id},
        {"id": 2, "name": "Bar", "file_path": "src/bar.py", "line": 20, "cst_node_id": None},
        {"id": 3, "name": "Baz", "file_path": "src/baz.py", "line": 30, "cst_node_id": ""},
        {"id": 4, "name": "Qux", "file_path": "src/qux.py", "line": 40, "cst_node_id": "invalid"},
        {"id": 5, "name": "NoPath", "line": 50, "cst_node_id": valid_id},  # dropped: no file_path
    ]
    entities = _normalize_entities(rows)
    assert len(entities) == 4
    by_name = {e["name"]: e for e in entities}
    assert "NoPath" not in by_name
    assert by_name["Foo"]["cst_node_id"] == valid_id
    # missing / empty / invalid all normalize to None, but the entity is kept
    assert by_name["Bar"]["cst_node_id"] is None
    assert by_name["Baz"]["cst_node_id"] is None
    assert by_name["Qux"]["cst_node_id"] is None


def test_normalize_entities_empty_input() -> None:
    """Empty rows list returns empty entities."""
    assert _normalize_entities([]) == []


def test_normalize_entities_all_valid() -> None:
    """All rows with valid cst_node_id are returned with file_path and cst_node_id."""
    id1 = str(uuid.uuid4())
    id2 = str(uuid.uuid4())
    rows = [
        {"file_path": "a.py", "cst_node_id": id1, "name": "A"},
        {"file_path": "b.py", "cst_node_id": id2, "name": "B"},
    ]
    entities = _normalize_entities(rows)
    assert len(entities) == 2
    for e in entities:
        assert "file_path" in e
        assert "cst_node_id" in e
        assert _is_valid_uuid4(e["cst_node_id"])
