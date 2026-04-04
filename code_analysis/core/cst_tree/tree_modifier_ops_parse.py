"""
Parse code snippets into CST statements for tree modifier operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Union, cast

import libcst as cst

# Node types for replace/delete that resolve by exact span (no promotion to
# enclosing Module/IndentedBlock statement).
FINE_GRAINED_REPLACE_NODE_TYPES = frozenset({"Param", "Name"})


def _snippet_as_string(code: Optional[str], code_lines: Optional[List[str]]) -> str:
    if code_lines is not None:
        if code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        return "\n".join(code_lines)
    if code is None:
        return ""
    return code


def parse_param_snippet(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> cst.Param:
    """
    Parse a single function parameter (e.g. ``self``, ``x: int``, ``*args``)
    for leaf Param replacement.
    """
    raw = _snippet_as_string(code, code_lines)
    if not raw.strip():
        raise ValueError("Param replacement code is empty")
    normalized = _normalize_snippet_indentation(raw)
    wrapped = f"def __leaf_param__({normalized.strip()}): pass\n"
    try:
        mod = cst.parse_module(wrapped)
    except cst.ParserSyntaxError as e:
        raise ValueError(f"Invalid parameter syntax: {e}") from e
    if not mod.body or not isinstance(mod.body[0], cst.FunctionDef):
        raise ValueError("Param snippet did not parse as a function parameter list")
    fd = mod.body[0]
    params = fd.params
    collected: List[cst.Param] = list(params.params)
    if params.star_arg and isinstance(params.star_arg, cst.Param):
        collected.append(params.star_arg)
    if params.kwonly_params:
        collected.extend(params.kwonly_params)
    if params.star_kwarg:
        collected.append(params.star_kwarg)
    if len(collected) != 1:
        raise ValueError(
            "Param replacement must expand to exactly one parameter; "
            f"got {len(collected)}"
        )
    return collected[0]


def _normalize_snippet_indentation(code: str) -> str:
    lines = code.splitlines()
    if not lines:
        return code
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent
    if min_indent is None or min_indent == 0:
        return code
    normalized_lines: List[str] = []
    for line in lines:
        if line.strip():
            if len(line) >= min_indent:
                normalized_lines.append(line[min_indent:])
            else:
                normalized_lines.append(line)
        else:
            normalized_lines.append("")
    return "\n".join(normalized_lines)


def parse_code_snippet(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> list[cst.BaseStatement]:
    """
    Parse code snippet into list of statements.

    Supports both single statements and multi-line blocks.
    Handles indentation by normalizing it before parsing.

    Args:
        code: Code snippet to parse as single string (may have indentation).
        code_lines: Code snippet as list of lines (alternative to code).
                    Prevents JSON escaping issues with multi-line code.

    Returns:
        List of CST statements.

    Raises:
        ValueError: If code cannot be parsed or both code and code_lines are provided.

    Note:
        If code_lines is provided, it takes precedence over code.
        This allows passing multi-line code without JSON escaping issues.
    """
    # Prefer code_lines over code to avoid JSON escaping issues
    if code_lines is not None:
        if code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        code = "\n".join(code_lines)
    elif code is None:
        return []

    if not code.strip():
        return []

    normalized = _normalize_snippet_indentation(code)

    # Try parsing as module first
    try:
        mod = cst.parse_module(normalized)
        return list(mod.body)
    except cst.ParserSyntaxError:
        # If parsing as module fails, try wrapping in a function body
        # This handles cases where code is a statement sequence (not valid module-level)
        indented_lines = []
        for line in normalized.splitlines():
            if line.strip():
                indented_lines.append("    " + line)
            else:
                indented_lines.append("")
        func_body = "\n".join(indented_lines)
        func_wrapper = f"def _temp():\n{func_body}"

        try:
            mod = cst.parse_module(func_wrapper)
            if mod.body and isinstance(mod.body[0], cst.FunctionDef):
                func = mod.body[0]
                if isinstance(func.body, cst.IndentedBlock):
                    return list(func.body.body)
        except Exception:
            pass

        # Last resort: try as single statement
        try:
            stmt = cst.parse_statement(normalized)
            return [stmt]
        except Exception as e:
            raise ValueError(
                f"Failed to parse code snippet as statements: {e}. "
                "Code must be valid Python statements."
            ) from e


def parse_code_snippet_or_comment(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> List[Union[cst.BaseStatement, cst.EmptyLine]]:
    """
    Parse code as statements, or as comment-only line(s) for insert.

    When the snippet is only comment(s) (e.g. "# mypy: ignore-errors"),
    parse_module returns empty body. This helper then builds EmptyLine+Comment
    node(s) so that insert can add comment lines to the module.

    Returns:
        List of statements or EmptyLine nodes (valid for Module.body).
    """
    statements = parse_code_snippet(code=code, code_lines=code_lines)
    if statements:
        return cast(List[Union[cst.BaseStatement, cst.EmptyLine]], statements)
    raw = ("\n".join(code_lines) if code_lines is not None else code) or ""
    stripped = raw.strip()
    if not stripped or not stripped.startswith("#"):
        return []
    # Comment-only: build EmptyLine(s) with Comment
    result: List[Union[cst.BaseStatement, cst.EmptyLine]] = []
    for line in stripped.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("#"):
            result.append(cst.EmptyLine(comment=cst.Comment(value=line_stripped)))
    return result
