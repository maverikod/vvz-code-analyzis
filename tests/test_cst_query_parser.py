"""
Tests for CSTQuery selector parser.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from code_analysis.cst_query import QueryParseError, parse_selector
from code_analysis.cst_query.ast import Combinator, PredicateOp, PseudoKind


def test_parse_simple_type() -> None:
    q = parse_selector("class")
    assert q.first.node_type == "class"
    assert q.rest == ()


def test_parse_predicates_and_pseudos() -> None:
    q = parse_selector('function[name="f"]:nth(0)')
    assert q.first.node_type == "function"
    assert q.first.predicates[0].attr == "name"
    assert q.first.predicates[0].op == PredicateOp.EQ
    assert q.first.predicates[0].value == "f"
    assert q.first.pseudos[0].kind == PseudoKind.NTH
    assert q.first.pseudos[0].index == 0


def test_parse_combinators_child_and_descendant() -> None:
    q = parse_selector('class[name="A"] > method[name="m"] stmt[type="Return"]')
    assert q.first.node_type == "class"
    assert q.rest[0][0] == Combinator.CHILD
    assert q.rest[0][1].node_type == "method"
    assert q.rest[1][0] == Combinator.DESCENDANT
    assert q.rest[1][1].node_type == "stmt"


def test_parse_unknown_pseudo_fails() -> None:
    with pytest.raises(QueryParseError):
        parse_selector("stmt:unknown()")
