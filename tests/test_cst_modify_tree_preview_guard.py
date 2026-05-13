"""Unit tests for cst_modify_tree_preview_guard."""

from __future__ import annotations

from code_analysis.commands.cst_modify_tree_preview_guard import (
    diff_span_exceeds_guard,
    original_changed_line_span,
)
from code_analysis.core.cst_tree.tree_builder import create_tree_from_code, remove_tree


def test_original_changed_line_span_single_line():
    a = "x = 1\ny = 2\n"
    b = "x = 9\ny = 2\n"
    assert original_changed_line_span(a, b) == (1, 1)


def test_diff_span_exceeds_guard_detects_runaway(tmp_path):
    src = "def f():\n    a = 1\n    b = 2\n"
    path = str(tmp_path / "guard.py")
    tree = create_tree_from_code(path, src)
    try:
        nid = next(
            k
            for k, m in tree.metadata_map.items()
            if m.start_line == 2 and m.type == "Assign"
        )
        mod = "def f():\n    a = 1\n    b = 999\n" + "z = 3\n" * 20
        msg = diff_span_exceeds_guard(src, mod, tree, (nid,), slack_lines=0)
        assert msg is not None
    finally:
        remove_tree(tree.tree_id)
