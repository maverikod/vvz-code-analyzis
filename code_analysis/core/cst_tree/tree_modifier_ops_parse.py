"""
Parse code snippets into CST statements for tree modifier operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Union, cast

import libcst as cst


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

    # Normalize indentation: find minimum common indentation and remove it
    lines = code.splitlines()
    if not lines:
        return []

    # Find minimum indentation (excluding empty lines)
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:  # Skip empty lines
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent

    # If all lines are empty or no indentation found, use original
    if min_indent is None or min_indent == 0:
        normalized = code
    else:
        # Remove minimum indentation from all lines
        normalized_lines = []
        for line in lines:
            if line.strip():  # Non-empty line
                if len(line) >= min_indent:
                    normalized_lines.append(line[min_indent:])
                else:
                    normalized_lines.append(line)
            else:  # Empty line
                normalized_lines.append("")
        normalized = "\n".join(normalized_lines)

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
