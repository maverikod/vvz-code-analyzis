"""
Chunked snapshot-node INSERT ops for sync_file_to_db_atomic (payload reduction).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.database.file_tree_sync import (
    FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE,
    _build_snapshot_node_insert_ops,
)


def test_snapshot_node_inserts_use_multi_row_values_per_chunk() -> None:
    rows = [
        ("n0", None, 0),
        ("n1", "n0", 0),
        ("n2", "n0", 1),
        ("n3", "n1", 0),
        ("n4", "n1", 1),
    ]
    ops = _build_snapshot_node_insert_ops(7, rows, chunk_size=2)
    assert len(ops) == 3
    assert [len(p) for _, p in ops] == [8, 8, 4]
    for sql, _params in ops:
        assert "INSERT INTO file_tree_snapshot_nodes" in sql
        assert "VALUES" in sql
        assert sql.count("SELECT id FROM file_tree_snapshots") == len(_params) // 4
    for _, params in ops:
        for j in range(0, len(params), 4):
            assert params[j] == 7
    assert ops[0][1] == (7, "n0", None, 0, 7, "n1", "n0", 0)
    assert ops[2][1] == (7, "n4", "n1", 1)


def test_snapshot_node_op_count_scales_with_chunk_not_row_count() -> None:
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
    assert _build_snapshot_node_insert_ops(1, []) == []


def test_single_row_one_insert_op() -> None:
    ops = _build_snapshot_node_insert_ops(99, [("root", None, 0)])
    assert len(ops) == 1
    sql, params = ops[0]
    assert "VALUES" in sql
    assert params == (99, "root", None, 0)
