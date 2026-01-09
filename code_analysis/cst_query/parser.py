"""
CSTQuery selector parser (Lark).

Supported features (intentionally minimal but practical):
- Steps: `TYPE` or `*`
- Combinators: descendant (space) and direct child (`>`)
- Predicates: [attr=value], [attr!=value], [attr~=value], [attr^=value], [attr$=value]
- Pseudos: :first, :last, :nth(N)

Notes:
- Values can be quoted with single or double quotes; unquoted barewords are allowed.
- Whitespace is insignificant except as descendant combinator.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from lark import Lark, Transformer, Token, UnexpectedInput

from .ast import (
    Combinator,
    Predicate,
    PredicateOp,
    Pseudo,
    PseudoKind,
    Query,
    SelectorStep,
)
from ..core.exceptions import QueryParseError


_GRAMMAR = r"""
?start: selector

selector: step ((CHILD step) | step)*
CHILD: ">"

step: node_type predicate* pseudo*
    | predicate+ pseudo*
    | pseudo+
node_type: STAR | NAME
STAR: "*"

predicate: "[" NAME OP value "]"
OP: "!=" | "~=" | "^=" | "$=" | "="
?value: STRING | BAREWORD

pseudo: ":" NAME pseudo_args?
pseudo_args: "(" INT ")"

NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
BAREWORD: /[^\]\s\)]+/
INT: /[0-9]+/

%import common.ESCAPED_STRING -> STRING
%import common.WS_INLINE -> WS
%ignore WS
"""


_parser = Lark(_GRAMMAR, parser="lalr", start="start")


@dataclass(frozen=True)
class _ParsedPseudo:
    name: str
    index: Optional[int]


class _ToAst(Transformer):
    def NAME(self, t: Token) -> str:  # noqa: N802
        return str(t)

    def INT(self, t: Token) -> int:  # noqa: N802
        return int(str(t))

    def STAR(self, _t: Token) -> str:  # noqa: N802
        return "*"

    def BAREWORD(self, t: Token) -> str:  # noqa: N802
        return str(t)

    def STRING(self, t: Token) -> str:  # noqa: N802
        # Lark keeps quotes; eval-like unescape via python string literal rules.
        raw = str(t)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            return bytes(raw[1:-1], "utf-8").decode("unicode_escape")
        return raw

    def OP(self, t: Token) -> str:  # noqa: N802
        return str(t)

    def predicate(self, items: list[Any]) -> Predicate:
        attr = str(items[0])
        op = PredicateOp(str(items[1]))
        val = str(items[2])
        return Predicate(attr=attr, op=op, value=val)

    def pseudo_args(self, items: list[Any]) -> int:
        return int(items[0])

    def pseudo(self, items: list[Any]) -> _ParsedPseudo:
        name = str(items[0])
        idx: Optional[int] = None
        if len(items) > 1:
            idx = int(items[1])
        return _ParsedPseudo(name=name, index=idx)

    def node_type(self, items: list[Any]) -> str:
        return str(items[0])

    def step(self, items: list[Any]) -> SelectorStep:
        node_type: str = "*"
        predicates: list[Predicate] = []
        pseudos: list[Pseudo] = []

        for it in items:
            if isinstance(it, str):
                node_type = it
            elif isinstance(it, Predicate):
                predicates.append(it)
            elif isinstance(it, _ParsedPseudo):
                pseudos.append(_pseudo_from_parsed(it))
            else:
                raise QueryParseError(f"Unexpected step item: {it!r}")

        return SelectorStep(
            node_type=node_type,
            predicates=tuple(predicates),
            pseudos=tuple(pseudos),
        )

    def selector(self, items: list[Any]) -> Query:
        if not items:
            raise QueryParseError("Empty selector")
        first = items[0]
        if not isinstance(first, SelectorStep):
            raise QueryParseError("Invalid selector start")

        rest: list[tuple[Combinator, SelectorStep]] = []
        i = 1
        while i < len(items):
            it = items[i]
            if isinstance(it, Token) and it.type == "CHILD":
                step = items[i + 1]
                if not isinstance(step, SelectorStep):
                    raise QueryParseError("Invalid selector sequence")
                rest.append((Combinator.CHILD, step))
                i += 2
                continue
            if isinstance(it, SelectorStep):
                rest.append((Combinator.DESCENDANT, it))
                i += 1
                continue
            raise QueryParseError("Invalid selector sequence")

        return Query(first=first, rest=tuple(rest))


def _pseudo_from_parsed(p: _ParsedPseudo) -> Pseudo:
    name = p.name.lower()
    if name == PseudoKind.FIRST.value:
        if p.index is not None:
            raise QueryParseError(":first does not accept arguments")
        return Pseudo(kind=PseudoKind.FIRST)
    if name == PseudoKind.LAST.value:
        if p.index is not None:
            raise QueryParseError(":last does not accept arguments")
        return Pseudo(kind=PseudoKind.LAST)
    if name == PseudoKind.NTH.value:
        if p.index is None:
            raise QueryParseError(":nth requires an integer argument, e.g. :nth(0)")
        return Pseudo(kind=PseudoKind.NTH, index=p.index)
    raise QueryParseError(f"Unsupported pseudo: {p.name}")


def parse_selector(selector: str) -> Query:
    """
    Parse a selector into a CSTQuery AST.

    Raises:
        QueryParseError
    """
    try:
        tree = _parser.parse(selector)
        return _ToAst().transform(tree)
    except UnexpectedInput as e:
        raise QueryParseError(f"Invalid selector: {e}") from e
