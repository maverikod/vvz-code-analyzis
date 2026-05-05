"""
CSTQuery AST models.

These data structures represent a parsed selector query.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


from __future__ import annotations


from dataclasses import dataclass

from enum import Enum

from typing import Optional
# @node-id: 47455b38-606b-430d-be2e-ee8a46b0fca3



class Combinator(str, Enum):
    """Selector step relation."""

    DESCENDANT = " "
    CHILD = ">"
# @node-id: 714f8fe0-0c3b-4801-a7d6-d30019878881

class PredicateOp(str, Enum):
    """Predicate operator for attribute tests."""

    EQ = "="
    NE = "!="
    CONTAINS = "~="
    PREFIX = "^="
    SUFFIX = "$="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
# @node-id: a0f17710-64b1-4ce2-ad13-ba0389d92033



@dataclass(frozen=True)
class Predicate:
    """Attribute predicate like [name="foo"] or [qualname^="A.B"]."""

    attr: str
    op: PredicateOp
    value: str
# @node-id: 6a98f09d-b290-48dd-a741-fa574a4d4f69

class PseudoKind(str, Enum):
    """Pseudo-class / functional pseudo."""

    FIRST = "first"
    LAST = "last"
    NTH = "nth"
    NOT = "not"
# @node-id: abd96f2e-d87a-4e8f-8827-b2d15037b84f



@dataclass(frozen=True)
class Pseudo:
    """Pseudo like :first, :last, :nth(0)."""

    kind: PseudoKind
    index: Optional[int] = None
# @node-id: 29e87898-658e-4d5d-bd95-03801193f2f0

@dataclass(frozen=True)
class SelectorStep:
    """
    A single selector step.

    `node_type` can be:
    - "*" (match anything)
    - alias: module, class, function, method, stmt, smallstmt, import
    - LibCST node class name (e.g. If, For, Try, With, Return)
    - "Type:*" for prefix/suffix match (e.g. Def:* -> FunctionDef, ClassDef)
    """

    node_type: str
    predicates: tuple[Predicate, ...] = ()
    pseudos: tuple[Pseudo, ...] = ()
    not_selector: Optional["Query"] = None
# @node-id: 501068c2-1c7f-494c-b50b-a006b8f6af67



@dataclass(frozen=True)
class Query:
    """A full query, e.g. class[name="A"] > function[name="m"] stmt[type="If"]."""

    first: SelectorStep
    rest: tuple[tuple[Combinator, SelectorStep], ...] = ()
