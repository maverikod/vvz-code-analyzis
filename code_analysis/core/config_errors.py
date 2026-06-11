"""
Human-readable configuration error reports (JSON syntax and validation).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

_LARK_LOCATION_RE = re.compile(
    r"at line (\d+), column (\d+)",
    re.IGNORECASE,
)
_EXPECTED_RSQB_RE = re.compile(r"Expected one of:.*RSQB", re.DOTALL)


def parse_json_error_location(message: str) -> tuple[Optional[int], Optional[int]]:
    """Extract 1-based line and column from a commentjson/lark error message."""
    match = _LARK_LOCATION_RE.search(message)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def suggest_json_syntax_fix(message: str) -> Optional[str]:
    """Return a short hint for common JSONC syntax mistakes."""
    if _EXPECTED_RSQB_RE.search(message):
        return (
            "An array was not closed: use ']' before '}'. "
            'Common mistake: "watch_dirs": [[ {...} ] — should be "watch_dirs": [ {...} ].'
        )
    if "TRAILING_COMMA" in message and "RSQB" in message:
        return "Check array brackets: ']' must close the list before the next '}'."
    if "Expecting property name" in message or "Expecting value" in message:
        return "Check for a missing comma between object properties or a stray trailing comma."
    return None


def format_config_snippet(
    text: str,
    line: int,
    *,
    radius: int = 2,
) -> List[str]:
    """Return numbered source lines around ``line`` (1-based)."""
    lines = text.splitlines()
    if not lines or line < 1 or line > len(lines):
        return []
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    out: List[str] = []
    for idx in range(start, end + 1):
        prefix = ">>" if idx == line else "  "
        out.append(f"{prefix} {idx:4d} | {lines[idx - 1]}")
    return out


def format_config_json_error_report(
    exc: Exception,
    *,
    config_path: Optional[Path] = None,
    source_text: Optional[str] = None,
) -> str:
    """
    Build a concise, actionable report for JSON/JSONC parse failures.

    No Python traceback — only location, hint, and a short source excerpt.
    """
    raw = str(exc)
    line, column = parse_json_error_location(raw)
    if line is None:
        line = getattr(exc, "line", None)
    if column is None:
        column = getattr(exc, "column", None)
    hint = suggest_json_syntax_fix(raw) or getattr(exc, "hint", None)

    parts: List[str] = ["Configuration file has invalid JSON syntax."]
    if config_path is not None:
        parts.append(f"File: {config_path}")

    if line is not None:
        loc = f"Location: line {line}"
        if column is not None:
            loc += f", column {column}"
        parts.append(loc)

    if hint:
        parts.append(f"Hint: {hint}")

    if source_text is None and config_path is not None and config_path.is_file():
        try:
            source_text = config_path.read_text(encoding="utf-8")
        except OSError:
            source_text = None

    if source_text and line is not None:
        snippet = format_config_snippet(source_text, line)
        if snippet:
            parts.append("Context:")
            parts.extend(snippet)

    parts.append(
        "Validate after fixing: casmgr-config-validate --file "
        + (str(config_path) if config_path else "<config.json>")
    )
    return "\n".join(parts)


def format_validation_result_line(result: Any) -> str:
    """Format one validator ``ValidationResult`` as a single readable line."""
    section = getattr(result, "section", None) or "config"
    key = getattr(result, "key", None)
    message = getattr(result, "message", str(result))
    suggestion = getattr(result, "suggestion", None)

    if key:
        loc = f"{section}.{key}"
    else:
        loc = str(section)

    line = f"[{loc}] {message}"
    if suggestion:
        line += f" — {suggestion}"
    return line


def format_validation_error_report(
    results: Sequence[Any],
    *,
    config_path: Optional[Path] = None,
    include_warnings: bool = False,
) -> str:
    """Format semantic validation failures without tracebacks."""
    errors = [r for r in results if getattr(r, "level", "") == "error"]
    warnings = [r for r in results if getattr(r, "level", "") == "warning"]

    if not errors and not (include_warnings and warnings):
        return "Configuration validation passed."

    parts: List[str] = []
    if errors:
        parts.append(
            f"Configuration validation failed: {len(errors)} error(s)"
            + (f" in {config_path}" if config_path else "")
            + "."
        )
        for idx, err in enumerate(errors, start=1):
            parts.append(f"  {idx}. {format_validation_result_line(err)}")
    else:
        parts.append("Configuration validation warnings:")

    if include_warnings and warnings:
        parts.append(f"Warnings ({len(warnings)}):")
        for idx, warn in enumerate(warnings, start=1):
            parts.append(f"  {idx}. {format_validation_result_line(warn)}")

    parts.append(
        "Fix the issues above, then run: casmgr-config-validate --file "
        + (str(config_path) if config_path else "<config.json>")
    )
    return "\n".join(parts)


def print_config_error(message: str, *, use_stderr: bool = True) -> None:
    """Print a multi-line config error report."""
    import sys

    stream = sys.stderr if use_stderr else sys.stdout
    print(message, file=stream)
