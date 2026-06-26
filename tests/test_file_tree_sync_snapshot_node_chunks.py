"""
Chunked snapshot-node INSERT ops for sync_file_to_db_atomic (payload reduction).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from types import SimpleNamespace

from code_analysis.core.database.file_tree_sync import (
    FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE,
    _build_snapshot_node_insert_ops,
    _build_snapshot_node_rows,
)


def test_snapshot_node_inserts_use_multi_row_values_per_chunk() -> None:
    """Verify test snapshot node inserts use multi row values per chunk."""
    rows = [
        ("n0", None, 0),
        ("n1", "n0", 0),
        ("n2", "n0", 1),
        ("n3", "n1", 0),
        ("n4", "n1", 1),
    ]
    ops = _build_snapshot_node_insert_ops(7, rows, chunk_size=2)
    assert len(ops) == 3
    # Each row binds (row_uuid, snapshot_id, node_id, parent_node_id, child_index).
    assert [len(p) for _, p in ops] == [10, 10, 5]
    for sql, _params in ops:
        assert "INSERT INTO file_tree_snapshot_nodes" in sql
        assert "VALUES" in sql
    for _, params in ops:
        for j in range(0, len(params), 5):
            assert params[j + 1] == 7
    p0 = ops[0][1]
    assert p0[1] == 7 and p0[2] == "n0" and p0[3] is None and p0[4] == 0
    assert p0[6] == 7 and p0[7] == "n1" and p0[8] == "n0" and p0[9] == 0
    p2 = ops[2][1]
    assert p2[1] == 7 and p2[2] == "n4" and p2[3] == "n1" and p2[4] == 1


def test_snapshot_node_op_count_scales_with_chunk_not_row_count() -> None:
    """Verify test snapshot node op count scales with chunk not row count."""
    n = 450
    rows = [(f"id{i}", f"p{i}" if i else None, i % 5) for i in range(n)]
    ops = _build_snapshot_node_insert_ops(1, rows)
    expected_batches = (n + FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE - 1) // (
        FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE
    )
    assert len(ops) == expected_batches
    # Would have been N ops with one-row inserts
    assert len(ops) < n


def test_empty_node_rows_yields_no_ops() -> None:
    """Verify test empty node rows yields no ops."""
    assert _build_snapshot_node_insert_ops(1, []) == []


def test_single_row_one_insert_op() -> None:
    """Verify test single row one insert op."""
    ops = _build_snapshot_node_insert_ops(99, [("root", None, 0)])
    assert len(ops) == 1
    sql, params = ops[0]
    assert "VALUES" in sql
    assert len(params) == 5
    assert params[1] == 99
    assert params[2] == "root"
    assert params[3] is None
    assert params[4] == 0


def _meta(node_id: str, children_ids: list[str]) -> SimpleNamespace:
    """Return meta."""
    return SimpleNamespace(node_id=node_id, children_ids=children_ids)


def test_build_snapshot_node_rows_orphan_not_in_children_ids_gets_unique_index() -> (
    None
):
    """Regression: default child_index=0 for missing entries caused UNIQUE violations."""
    tree = SimpleNamespace(
        metadata_map={
            "root": _meta("root", ["a", "b"]),
            "a": _meta("a", []),
            "b": _meta("b", []),
            "orphan": _meta("orphan", []),
        },
        parent_map={
            "root": None,
            "a": "root",
            "b": "root",
            "orphan": "root",
        },
    )
    rows = _build_snapshot_node_rows(tree, 0)
    by_nid = {r[0]: (r[1], r[2]) for r in rows}
    assert by_nid["root"] == (None, 0)
    assert by_nid["a"] == ("root", 0)
    assert by_nid["b"] == ("root", 1)
    assert by_nid["orphan"] == ("root", 2)


def test_build_snapshot_node_rows_duplicate_child_id_in_list_assigns_once() -> None:
    """Verify test build snapshot node rows duplicate child id in list assigns once."""
    tree = SimpleNamespace(
        metadata_map={
            "root": _meta("root", ["a", "a", "b"]),
            "a": _meta("a", []),
            "b": _meta("b", []),
        },
        parent_map={"root": None, "a": "root", "b": "root"},
    )
    rows = _build_snapshot_node_rows(tree, 0)
    by_nid = {r[0]: r[2] for r in rows if r[1] == "root"}
    assert by_nid["a"] == 0
    assert by_nid["b"] == 1
