"""Unit tests for text-format unified-tree routing helpers."""

from __future__ import annotations

from code_analysis.core.edit_session.edit_operations_adapter import (
    text_ops_use_unified_tree,
)


def test_text_ops_use_unified_tree_accepts_target_node_id_insert() -> None:
    """Verify test text ops use unified tree accepts target node id insert."""
    ops = [
        {
            "type": "insert",
            "target_node_id": "91",
            "position": "before",
            "content": "x",
        }
    ]
    assert text_ops_use_unified_tree(ops) is True


def test_text_ops_use_unified_tree_rejects_line_only_insert() -> None:
    """Verify test text ops use unified tree rejects line only insert."""
    ops = [{"type": "insert", "start_line": 3, "content": "x"}]
    assert text_ops_use_unified_tree(ops) is False


def test_text_ops_use_unified_tree_accepts_after_node_id() -> None:
    """Verify test text ops use unified tree accepts after node id."""
    ops = [{"type": "insert", "after_node_id": "5", "content": "x"}]
    assert text_ops_use_unified_tree(ops) is True
