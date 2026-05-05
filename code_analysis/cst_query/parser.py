"""
CSTQuery selector parser (Lark).

Supported features (intentionally minimal but practical):
- Steps: `TYPE`, `TYPE:*` (prefix/suffix match on node type), or `*`
- Combinators: descendant (space) and direct child (`>`)
- Predicates: [attr=value], [attr!=value], [attr~=value], [attr^=value], [attr$=value]
- Pseudos: :first, :last, :nth(N)

Type modifier `:*` matches by prefix or suffix: e.g. `Def:*` → FunctionDef, ClassDef.

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

selector: dslash_step ((CHILD step) | step)*
        | step ((CHILD step) | step)*
CHILD: ">"
DSLASH: "//"

dslash_step: DSLASH step

step: node_type predicate* pseudo*
    | predicate+ pseudo*
    | pseudo+
node_type: STAR | NAME type_wildcard?
type_wildcard: ":*"
STAR: "*"

predicate: "[" AT? NAME OP value "]"
AT: "@"
OP: ">=" | "<=" | "!=" | "~=" | "^=" | "$=" | ">" | "<" | "="
?value: STRING | BAREWORD

pseudo: ":" NAME pseudo_args?
pseudo_args: "(" INT ")"
           | "(" selector ")"

NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
BAREWORD: /[^\]\s\)]+/
INT: /[0-9]+/

%import common.ESCAPED_STRING -> STRING
%import common.WS_INLINE -> WS
%ignore WS
"""



_parser = Lark(_GRAMMAR, parser="lalr", start="start")
# @node-id: ad1bd1c6-138b-411e-83a0-34db5f35c442



@dataclass(frozen=True)
class _ParsedPseudo:
    name: str
    index: Optional[int]
# @node-id: ddb378c9-fcc1-4538-9c65-43faa0f5fe3b

class _ToAst:
    # @node-id: 8112ede7-f8eb-474f-83c0-450c73154047
    
    
    def NAME(self, t: Token) -> str:  # noqa: N802
        return str(t)
    # @node-id: ca73e612-e373-47e4-9122-61c0e359c0d4
    
    
    def INT(self, t: Token) -> int:  # noqa: N802
        return int(str(t))
    # @node-id: d182063d-d7d7-42ea-967d-d425bbb75acb
    
    
    def STAR(self, _t: Token) -> str:  # noqa: N802
        return "*"
    # @node-id: e2165a0f-a0f0-4855-91bf-156e721873fd
    
    
    def BAREWORD(self, t: Token) -> str:  # noqa: N802
        """Parse bareword value, handling quoted strings that were parsed as barewords.
    
            Sometimes quoted strings (especially single quotes inside double-quoted
            Python strings) are parsed as BAREWORD instead of STRING.
            We need to detect and handle these cases.
            """
        raw = str(t)
        # Check if it looks like a quoted string (starts and ends with same quote)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            # Remove quotes and decode escape sequences
            unquoted = raw[1:-1]
            try:
                return bytes(unquoted, "utf-8").decode("unicode_escape")
            except (UnicodeDecodeError, UnicodeError):
                return unquoted
        return raw
    # @node-id: a9f06d3f-e888-4515-aca9-69388b72fe98
    
    
    def STRING(self, t: Token) -> str:  # noqa: N802
        """Parse string value, removing quotes and handling escape sequences.
    
            Lark provides the string token with quotes included.
            We need to remove the outer quotes and decode escape sequences.
            """
        raw = str(t)
        # Remove outer quotes if present (both single and double quotes supported)
        if len(raw) >= 2:
            if raw[0] == raw[-1] and raw[0] in ("'", '"'):
                # Remove quotes and decode escape sequences
                unquoted = raw[1:-1]
                try:
                    # Decode escape sequences (e.g., \\n -> \n, \\' -> \')
                    return bytes(unquoted, "utf-8").decode("unicode_escape")
                except (UnicodeDecodeError, UnicodeError):
                    # If decoding fails, return unquoted string as-is
                    return unquoted
        return raw
    # @node-id: 1a82f31f-a7b0-4505-8999-d243239f8a6a
    
    
    def OP(self, t: Token) -> str:  # noqa: N802
        return str(t)
    # @node-id: da19daf7-65f6-41a2-b65f-18b026baeeeb
    
    def predicate(self, items: list[Any]) -> Predicate:
        # items: [AT?, NAME, OP, value] — AT is optional and discarded
        filtered = [it for it in items if not (isinstance(it, Token) and it.type == "AT")]
        attr, op_str, value = str(filtered[0]), str(filtered[1]), str(filtered[2])
        return Predicate(attr=attr, op=PredicateOp(op_str), value=value)
    # @node-id: 642a322e-78b0-4251-855f-b8cd61c7b0ae
    
    def pseudo_args(self, items: list[Any]) -> Any:
        # Either INT (for :nth) or a Query (for :not)
        if items and isinstance(items[0], int):
            return items[0]
        if items and isinstance(items[0], Query):
            return items[0]
        return items[0] if items else None
    # @node-id: 0fe55623-da59-4a9b-afa4-c0007f75bcb4
    
    
    def pseudo(self, items: list[Any]) -> _ParsedPseudo:
        name = str(items[0])
        idx: Optional[int] = None
        if len(items) > 1:
            idx = int(items[1])
        return _ParsedPseudo(name=name, index=idx)
    # @node-id: 10c8620e-15ca-41db-902b-bbcbdacef41c
    
    
    def node_type(self, items: list[Any]) -> str:
        name = str(items[0])
        if len(items) > 1:
            return name + ":*"
        return name
    # @node-id: 5b5a3379-470b-44bd-a07f-a1cb67e2af3a
    
    def step(self, items: list[Any]) -> SelectorStep:
        node_type: str = "*"
        predicates: list[Predicate] = []
        pseudos: list[Pseudo] = []
        not_selector: Any = None
    
        for it in items:
            if isinstance(it, str):
                node_type = it
            elif isinstance(it, Predicate):
                predicates.append(it)
            elif isinstance(it, _ParsedPseudo):
                p = _pseudo_from_parsed(it)
                if p.kind == PseudoKind.NOT:
                    not_selector = it.not_query
                else:
                    pseudos.append(p)
            else:
                raise QueryParseError(f"Unexpected step item: {it!r}")
    
        return SelectorStep(
            node_type=node_type,
            predicates=tuple(predicates),
            pseudos=tuple(pseudos),
            not_selector=not_selector,
        )
    # @node-id: 1d936fb7-65af-4f3d-8bf4-c0f055d6c38b
    
    
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
    
# @node-id: a985f9fd-98cb-4f63-bb6e-b61e7c7a01eb


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
# @node-id: cf6062f2-1ff0-4289-bcbe-2ec5d7e6a926



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
