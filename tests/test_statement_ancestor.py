"""Tests for statement ancestor helpers and cst_get_node_at_line statement_level."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.cst_get_node_at_line_command import CSTGetNodeAtLineCommand
from code_analysis.core.cst_tree.statement_ancestor import (
    annotate_statement_source,
    find_statement_ancestor_node_id,
)
from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
from code_analysis.core.cst_tree.tree_range_finder import find_node_by_range


def test_annotate_statement_source_short() -> None:
    out = annotate_statement_source("a = 1\nb = 2", start_line=10)
    assert out == "10\ta = 1\n11\tb = 2"


def test_annotate_statement_source_truncates() -> None:
    lines = [f"x = {i}" for i in range(100)]
    src = "\n".join(lines)
    out = annotate_statement_source(src, start_line=1, max_lines=10)
    out_lines = out.split("\n")
    assert len(out_lines) <= 10
    assert out_lines[0] == "1\tx = 0"
    assert any("lines omitted" in ln for ln in out_lines)
    assert out_lines[-1].endswith("x = 99")


def test_find_statement_ancestor_assign_from_leaf(tmp_path: Path) -> None:
    src = "def f():\n    y = 1\n"
    tree = create_tree_from_code(str(tmp_path / "x.py"), src)
    leaf = find_node_by_range(tree.tree_id, 2, 2, prefer_exact=False)
    assert leaf is not None
    sid, fb = find_statement_ancestor_node_id(tree, leaf.node_id)
    assert fb is False
    stmt = tree.metadata_map[sid]
    assert stmt.type == "Assign"


def test_cst_get_node_at_line_includes_statement_and_leaf(tmp_path: Path) -> None:
    p = tmp_path / "m.py"
    src = "def g():\n    z = 2\n"
    p.write_text(src, encoding="utf-8")
    tree = create_tree_from_code(str(p.resolve()), src)
    cmd = CSTGetNodeAtLineCommand()
    res = asyncio.run(cmd.execute(tree_id=tree.tree_id, line=2, statement_level=True))
    assert isinstance(res, SuccessResult)
    data = res.data
    assert "statement" in data
    assert data["statement"]["type"] == "Assign"
    assert "\t" in data["statement"]["source"]
    assert "leaf" in data
    assert data["leaf"]["type"]  # deepest node (e.g. Name or literal)
    res2 = asyncio.run(cmd.execute(tree_id=tree.tree_id, line=2, statement_level=False))
    assert isinstance(res2, SuccessResult)
    assert "statement" not in res2.data
    assert "leaf" not in res2.data
