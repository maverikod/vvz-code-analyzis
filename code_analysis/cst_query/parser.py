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
# @node-id: c79e0a29-3f68-41e9-a396-a556b6ea0c96

class _ToAst:
    # @node-id: ae1ec6dc-7764-4dec-af8f-035b00ec4db4
    
    
    
    
    def NAME(self, t: Token) -> str:  # noqa: N802
        return str(t)
    # @node-id: b7d12d2a-4763-45d4-98db-2019c1e3bd4c
    
    
    
    def INT(self, t: Token) -> int:  # noqa: N802
        return int(str(t))
    # @node-id: 459efaf2-0f7f-4a49-b945-bc9a0b9cfe7e
    
    
    
    def STAR(self, _t: Token) -> str:  # noqa: N802
        return "*"
    # @node-id: 825a40ca-51c1-4c75-bdbe-061ea78bf425
    
    
    
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
    # @node-id: ff148399-6f95-408c-8b76-99f7bcd4922c
    
    
    
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
    # @node-id: 24e72091-5380-4cfc-b838-6a06bea40b88
    
    
    
    def OP(self, t: Token) -> str:  # noqa: N802
        return str(t)
    # @node-id: 2b524622-7f50-49b3-8b01-2eda167448bf
    
    
    def predicate(self, items: list[Any]) -> Predicate:
        # items: [AT?, NAME, OP, value] — AT is optional and discarded
        filtered = [it for it in items if not (isinstance(it, Token) and it.type == "AT")]
        attr, op_str, value = str(filtered[0]), str(filtered[1]), str(filtered[2])
        return Predicate(attr=attr, op=PredicateOp(op_str), value=value)
    # @node-id: eb018f86-9ff0-4caf-b01b-0ca441a4c899
    def dslash_step(self, items: list[Any]) -> SelectorStep:
        """Transform //step: return the inner SelectorStep directly.

    Grammar rule `dslash_step: DSLASH step` gives [DSLASH_token, SelectorStep].
    The `selector` rule then treats this SelectorStep as the leading step of
    a descendant search (starting from root wildcard).
    """
        inner = next((it for it in items if isinstance(it, SelectorStep)), None)
        if inner is None:
            raise QueryParseError("dslash_step: expected SelectorStep")
        return inner
    # @node-id: 3db05f77-8890-4d9a-96e7-b71edfd81519
    
    
    def pseudo_args(self, items: list[Any]) -> Any:
        # Either INT (for :nth) or a Query (for :not)
        if items and isinstance(items[0], int):
            return items[0]
        if items and isinstance(items[0], Query):
            return items[0]
        return items[0] if items else None
    # @node-id: a46404ed-bcd9-4e26-a353-127e522013b6
    
    def pseudo(self, items: list[Any]) -> _ParsedPseudo:
        name = str(items[0])
        arg = items[1] if len(items) > 1 else None
        if isinstance(arg, int):
            return _ParsedPseudo(name=name, index=arg)
        if isinstance(arg, Query):
            return _ParsedPseudo(name=name, index=None, not_query=arg)
        return _ParsedPseudo(name=name, index=None)
    # @node-id: a75225bd-7759-4de9-97bc-c0434a5b66c3
    
    
    
    def node_type(self, items: list[Any]) -> str:
        name = str(items[0])
        if len(items) > 1:
            return name + ":*"
        return name
    # @node-id: 9abe1c42-bec3-4e53-b1ac-9ddff0d9c298
    
    
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
    # @node-id: 6b3b495e-497e-43bb-82af-d93991403ad6
    
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
    
    
    
# @node-id: e1695844-4214-4bb1-9465-a4aec2162403
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
# @node-id: 837efd5d-d9d6-447c-85de-76e9cb0d04f4




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
