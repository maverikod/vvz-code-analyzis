"""Tests for human-readable configuration error reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.config_errors import (
    format_config_json_error_report,
    format_validation_error_report,
    suggest_json_syntax_fix,
)
from code_analysis.core.config_json import ConfigJSONDecodeError, load_config_json_text


def test_suggest_json_syntax_fix_missing_array_close() -> None:
    """Verify test suggest json syntax fix missing array close."""
    msg = "Expected one of: \n        * TRAILING_COMMA\n        * RSQB"
    hint = suggest_json_syntax_fix(msg)
    assert hint is not None
    assert "watch_dirs" in hint or "']'" in hint


def test_format_config_json_error_report_includes_context() -> None:
    """Verify test format config json error report includes context."""
    text = """{
  "worker": {
    "watch_dirs": [[
      {"id": "x", "path": "/tmp"}
    }
  }
}
"""
    exc = ConfigJSONDecodeError(
        "parse failed at line 5",
        source_text=text,
        line=5,
        column=5,
    )
    report = format_config_json_error_report(exc, source_text=text)
    assert "json syntax" in report.lower()
    assert "line 5" in report
    assert ">>" in report
    assert "casmgr-config-validate" in report


def test_load_config_json_text_bad_watch_dirs(tmp_path: Path) -> None:
    """Verify test load config json text bad watch dirs."""
    path = tmp_path / "config.json"
    path.write_text(
        '{"code_analysis":{"worker":{"watch_dirs":[[{"id":"a","path":"/x"}]}}}}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigJSONDecodeError) as exc_info:
        load_config_json_text(path.read_text(encoding="utf-8"), source_path=path)
    report = str(exc_info.value)
    assert "Hint:" in report
    assert "Context:" in report


def test_format_validation_error_report() -> None:
    """Verify test format validation error report."""

    class _R:
        """Represent R."""

        level = "error"
        section = "code_analysis.worker"
        key = "watch_dirs"
        message = "watch_dirs must be a list of objects"
        suggestion = 'Use [{"id": "...", "path": "..."}]'

    report = format_validation_error_report(
        [_R()], config_path=Path("/etc/casmgr/config.json")
    )
    assert "1 error" in report
    assert "watch_dirs" in report
    assert "casmgr-config-validate" in report
