"""
Integration tests: CSTQuery -> compose (apply_replace_ops).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast

import pytest

from code_analysis.core.cst_module_tools import ReplaceOp, Selector, apply_replace_ops
from code_analysis.core.cst_module_tools import CSTModulePatchError
from code_analysis.cst_query import query_source


def test_apply_replace_ops_with_cst_query_replaces_return_smallstmt() -> None:
    src = """
def f(x: int) -> int:
    y = x + 1
    return y
"""
    ops = [
        ReplaceOp(
            selector=Selector(kind="cst_query", query='smallstmt[type="Return"]'),
            new_code="return 123",
        )
    ]
    new_src, stats = apply_replace_ops(src, ops)
    assert stats["replaced"] == 1
    assert "return 123" in new_src
    ast.parse(new_src)  # valid python


def test_apply_replace_ops_with_node_id_replaces_return_smallstmt() -> None:
    src = """
def f(x: int) -> int:
    y = x + 1
    return y
"""
    m = query_source(src, 'smallstmt[type="Return"]')[0]
    ops = [
        ReplaceOp(
            selector=Selector(kind="node_id", node_id=m.node_id),
            new_code="return 999",
        )
    ]
    new_src, stats = apply_replace_ops(src, ops)
    assert stats["replaced"] == 1
    assert "return 999" in new_src
    ast.parse(new_src)


def test_smallstmt_snippet_must_be_single_line() -> None:
    src = "def f():\n    return 1\n"
    m = query_source(src, 'smallstmt[type="Return"]')[0]
    ops = [
        ReplaceOp(
            selector=Selector(kind="node_id", node_id=m.node_id),
            new_code="if True:\n    return 2\n",
        )
    ]
    with pytest.raises(CSTModulePatchError):
        apply_replace_ops(src, ops)
