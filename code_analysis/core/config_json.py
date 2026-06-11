"""
Load ``config.json`` with ``#`` and ``//`` comments (JSONC-style).

Uses the ``commentjson`` package. Plain JSON without comments still parses.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import commentjson

from code_analysis.core.config_errors import (
    format_config_json_error_report,
    parse_json_error_location,
    suggest_json_syntax_fix,
)

_MCP_COMMENT_JSON_INSTALLED = False


class ConfigJSONDecodeError(ValueError):
    """Raised when a configuration file is not valid JSON/JSONC."""

    def __init__(
        self,
        message: str,
        *,
        source_path: Optional[Path] = None,
        source_text: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
        hint: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.source_path = source_path
        self.source_text = source_text
        self.line = line
        self.column = column
        self.hint = hint


def load_config_json_text(
    text: str,
    *,
    source_path: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Parse configuration text that may contain ``#`` or ``//`` comments.

    Args:
        text: File contents.
        source_path: Optional path for error reports.

    Returns:
        Parsed root object (must be a JSON object).

    Raises:
        ConfigJSONDecodeError: On parse failure or non-object root.
    """
    try:
        data = commentjson.loads(text)
    except Exception as exc:
        line, column = parse_json_error_location(str(exc))
        hint = suggest_json_syntax_fix(str(exc))
        report = format_config_json_error_report(
            exc,
            config_path=source_path,
            source_text=text,
        )
        raise ConfigJSONDecodeError(
            report,
            source_path=source_path,
            source_text=text,
            line=line,
            column=column,
            hint=hint,
        ) from exc
    if not isinstance(data, dict):
        raise ConfigJSONDecodeError(
            "Configuration root must be a JSON object (not an array or scalar).",
            source_path=source_path,
            source_text=text,
        )
    return data


def load_config_json(path: Union[str, Path]) -> dict[str, Any]:
    """
    Read and parse a configuration file from disk.

    Args:
        path: Path to ``config.json`` (or equivalent).

    Returns:
        Parsed configuration dict.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ConfigJSONDecodeError: On parse failure.
        RuntimeError: On other read errors.
    """
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise RuntimeError(
            f"Error reading configuration file {config_path}: {exc}"
        ) from exc
    return load_config_json_text(text, source_path=config_path)


_MCP_SIMPLE_CONFIG_PATCHED = False


def install_comment_json_for_mcp_adapter() -> None:
    """
    Patch mcp-proxy-adapter ``SimpleConfig.load`` to accept commented JSON.

    Idempotent; safe to call more than once. Must run before ``SimpleConfig.load()``.

    Does not replace ``json.loads`` on the stdlib ``json`` module (that breaks
    ``commentjson`` itself, which delegates to ``json.loads`` after stripping comments).
    """
    global _MCP_COMMENT_JSON_INSTALLED, _MCP_SIMPLE_CONFIG_PATCHED
    if _MCP_COMMENT_JSON_INSTALLED:
        return

    from mcp_proxy_adapter.core.config.simple_config import SimpleConfig
    import mcp_proxy_adapter.core.config.simple_config as sc_mod

    if _MCP_SIMPLE_CONFIG_PATCHED:
        _MCP_COMMENT_JSON_INSTALLED = True
        return

    _orig_simple_load = SimpleConfig.load

    def load_with_comments(self: Any) -> Any:
        content = load_config_json(self.config_path)
        orig_loads = sc_mod.json.loads
        sc_mod.json.loads = lambda *_args, **_kwargs: content
        try:
            return _orig_simple_load(self)
        finally:
            sc_mod.json.loads = orig_loads

    SimpleConfig.load = load_with_comments  # type: ignore[method-assign]
    _MCP_SIMPLE_CONFIG_PATCHED = True
    _MCP_COMMENT_JSON_INSTALLED = True
