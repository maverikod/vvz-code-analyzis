"""
Load ``config.json`` with ``#`` and ``//`` comments (JSONC-style).

Uses the ``commentjson`` package. Plain JSON without comments still parses.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import tempfile
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
        """Initialize the instance."""
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

    Implementation note: this NEVER reassigns ``json.loads``/``json.load`` (or any
    other attribute) on the stdlib ``json`` module. That process-global module is
    shared by every thread; briefly replacing ``json.loads`` with a closure that
    returns a fixed (and, worse, still-being-mutated) dict is a race condition —
    any unrelated thread calling ``json.load``/``json.loads`` during the window
    gets the wrong data instead of the file it asked for. Instead, comments are
    stripped up front via :func:`load_config_json` (``commentjson``), the result
    is re-serialized as plain JSON into a private temporary file, and the
    *instance's* ``config_path`` is pointed at that temp file for the duration of
    a single call to the original, unmodified ``SimpleConfig.load``. Only the
    calling instance's own attribute is touched (restored in ``finally``), so
    concurrent, unrelated ``SimpleConfig.load``/``json.load`` calls are
    unaffected. Each call site here creates a fresh ``SimpleConfig`` instance
    immediately before calling ``.load()`` (see ``main_config.py`` and
    ``config_validator/validator.py``), so there is no shared-instance hazard.
    """
    global _MCP_COMMENT_JSON_INSTALLED, _MCP_SIMPLE_CONFIG_PATCHED
    if _MCP_COMMENT_JSON_INSTALLED:
        return

    from mcp_proxy_adapter.core.config.simple_config import SimpleConfig

    if _MCP_SIMPLE_CONFIG_PATCHED:
        _MCP_COMMENT_JSON_INSTALLED = True
        return

    _orig_simple_load = SimpleConfig.load

    def load_with_comments(self: Any) -> Any:
        """Strip comments into a private temp file, then run the real loader."""
        content = load_config_json(self.config_path)
        stripped_text = json.dumps(content)

        original_config_path = self.config_path
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix="code_analysis_config_stripped_",
            suffix=".json",
        )
        tmp_path = Path(tmp_name)
        try:
            with open(tmp_fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(stripped_text)
            self.config_path = tmp_path
            return _orig_simple_load(self)
        finally:
            self.config_path = original_config_path
            tmp_path.unlink(missing_ok=True)

    SimpleConfig.load = load_with_comments  # type: ignore[method-assign]
    _MCP_SIMPLE_CONFIG_PATCHED = True
    _MCP_COMMENT_JSON_INSTALLED = True
