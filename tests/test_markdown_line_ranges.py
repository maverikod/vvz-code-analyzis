"""Unit tests for markdown section line range resolution."""

from __future__ import annotations

from code_analysis.commands.universal_file_preview.errors import PreviewError
from code_analysis.commands.universal_file_preview.handlers.markdown_line_ranges import (
    resolve_markdown_line_range,
)

_LEAF_SECTION = """\
# Only Section

This section has body text but no sub-sections.
"""


def test_section_replace_range_includes_heading_line() -> None:
    bounds = resolve_markdown_line_range(_LEAF_SECTION, "only-section")
    assert not isinstance(bounds, PreviewError)
    start_line, end_line = bounds
    assert start_line == 1
    lines = _LEAF_SECTION.splitlines()
    assert lines[start_line - 1].startswith("# Only Section")
    assert end_line >= start_line


def test_content_suffix_range_excludes_heading_line() -> None:
    bounds = resolve_markdown_line_range(_LEAF_SECTION, "only-section/__content")
    assert not isinstance(bounds, PreviewError)
    start_line, _end_line = bounds
    assert start_line == 3
    assert (
        _LEAF_SECTION.splitlines()[start_line - 1]
        == "This section has body text but no sub-sections."
    )
