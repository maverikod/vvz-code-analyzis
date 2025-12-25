"""
Tests for CSTQuery executor (query_source).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.cst_query import query_source


def test_query_method_by_qualname_and_return_smallstmt() -> None:
    src = """
class A:
    def m(self, x: int) -> int:
        y = x + 1
        return y
"""
    # Find the return statement inside A.m
    matches = query_source(
        src,
        'method[qualname="A.m"] smallstmt[type="Return"]',
        include_code=False,
    )
    assert len(matches) == 1
    m = matches[0]
    assert m.kind == "smallstmt"
    assert m.node_type == "Return"
    assert m.qualname == "A.m"
    assert "smallstmt:" in m.node_id


def test_descendant_combinator_finds_nested_stmt() -> None:
    src = """
def f():
    if True:
        x = 1
        return x
"""
    # If is a statement node; descendant should find it under function
    matches = query_source(src, 'function[name="f"] stmt[type="If"]')
    assert len(matches) == 1
    assert matches[0].kind == "stmt"
    assert matches[0].node_type == "If"
