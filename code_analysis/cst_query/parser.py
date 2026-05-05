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
# @node-id: 3a4e8c0c-1240-475f-b1c9-30d6580d6630

@dataclass(frozen=True)
class _ParsedPseudo:
    name: str
    index: Optional[int]
    not_query: Optional["Query"] = None
# @node-id: eb82b23d-a243-4aff-9450-75aa65c0dde2

class _ToAst:
    # @node-id: 72611ff5-9aff-4d7e-bb63-9051d5d10d62
    
    
    
    
    def NAME(self, t: Token) -> str:  # noqa: N802
        return str(t)
    # @node-id: 180e49f5-8805-4db3-804a-68621cdeba07
    
    
    
    def INT(self, t: Token) -> int:  # noqa: N802
        return int(str(t))
    # @node-id: f85cb223-6b79-4eab-8472-18368754844a
    
    
    
    def STAR(self, _t: Token) -> str:  # noqa: N802
        return "*"
    # @node-id: 8feddf07-ae40-48a2-acfc-7db5ca597652
    
    
    
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
    # @node-id: f2da1145-eab9-4c8e-b604-6e035b474316
    
    
    
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
    # @node-id: eaa75272-799a-451b-aa24-0a409de4a60b
    
    
    
    def OP(self, t: Token) -> str:  # noqa: N802
        return str(t)
    # @node-id: 9574d197-6a78-404d-bf88-bab6e2721d0f
    
    
    def predicate(self, items: list[Any]) -> Predicate:
        # items: [AT?, NAME, OP, value] — AT is optional and discarded
        filtered = [it for it in items if not (isinstance(it, Token) and it.type == "AT")]
        attr, op_str, value = str(filtered[0]), str(filtered[1]), str(filtered[2])
        return Predicate(attr=attr, op=PredicateOp(op_str), value=value)
    # @node-id: cfb51e82-c904-4824-b1bc-dee27a5ed589
    
    
    def pseudo_args(self, items: list[Any]) -> Any:
        # Either INT (for :nth) or a Query (for :not)
        if items and isinstance(items[0], int):
            return items[0]
        if items and isinstance(items[0], Query):
            return items[0]
        return items[0] if items else None
    # @node-id: aea25e08-60c4-4e56-9bc8-00a343fee584
    
    def pseudo(self, items: list[Any]) -> _ParsedPseudo:
        name = str(items[0])
        arg = items[1] if len(items) > 1 else None
        if isinstance(arg, int):
            return _ParsedPseudo(name=name, index=arg)
        if isinstance(arg, Query):
            return _ParsedPseudo(name=name, index=None, not_query=arg)
        return _ParsedPseudo(name=name, index=None)
    # @node-id: a037c5a9-d899-43bf-93cb-5699d031d942
    
    
    
    def node_type(self, items: list[Any]) -> str:
        name = str(items[0])
        if len(items) > 1:
            return name + ":*"
        return name
    # @node-id: b0bdedaa-ec53-454b-a8fa-485b23d8dac3
    
    
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
    # @node-id: e7f5a0d4-99ac-4024-b48c-732ae329702e
    
    def selector(self, items: list[Any]) -> Query:
        if not items:
            raise QueryParseError("Empty selector")
        # dslash_step emits a wildcard SelectorStep before the real step
        # so items[0] is always a SelectorStep after transform
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
    
    
    
# @node-id: 4932b273-43e7-433c-b761-bfcea1bf67c8
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
        if not isinstance(p.index, int):
            raise QueryParseError(":nth requires an integer argument, e.g. :nth(0)")
        return Pseudo(kind=PseudoKind.NTH, index=p.index)
    if name == PseudoKind.NOT.value:
        return Pseudo(kind=PseudoKind.NOT)
    raise QueryParseError(f"Unsupported pseudo: {p.name}")
# @node-id: fae53247-00d0-4c56-a5c0-776d146cb777




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
