"""
Tests for ``text_ranges`` bracket syntax and validation (1-based inclusive lines).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.file_handlers.text_ranges import (
    LineRange,
    clamp_read_range,
    parse_bracket_range,
    parse_bracket_ranges,
    validate_range_against_length,
)


def test_parse_single_line_bracket() -> None:
    """Verify test parse single line bracket."""
    assert parse_bracket_range("[12]") == LineRange(12, 12)
    assert parse_bracket_range("  [ 7 ] ") == LineRange(7, 7)


def test_parse_closed_range_comma() -> None:
    """Verify test parse closed range comma."""
    assert parse_bracket_range("[12,15]") == LineRange(12, 15)


def test_parse_open_start() -> None:
    """Verify test parse open start."""
    assert parse_bracket_range("[:12]") == LineRange(1, 12)
    assert parse_bracket_range("[ : 3 ]") == LineRange(1, 3)


def test_parse_open_end_requires_total_lines() -> None:
    """Verify test parse open end requires total lines."""
    with pytest.raises(ValueError, match="total_lines is required"):
        parse_bracket_range("[11:]")


def test_parse_open_end_resolves_to_eof() -> None:
    """Verify test parse open end resolves to eof."""
    assert parse_bracket_range("[11:]", total_lines=20) == LineRange(11, 20)
    assert parse_bracket_range("[1:]", total_lines=1) == LineRange(1, 1)


def test_parse_empty_or_invalid() -> None:
    """Verify test parse empty or invalid."""
    with pytest.raises(ValueError, match="bracketed"):
        parse_bracket_range("")
    with pytest.raises(ValueError):
        parse_bracket_range("[]")
    with pytest.raises(ValueError, match="empty range"):
        parse_bracket_range("[  ]")
    with pytest.raises(ValueError, match="bracketed"):
        parse_bracket_range("12,15")
    with pytest.raises(ValueError, match="invalid range \\[:]"):
        parse_bracket_range("[:]")
    with pytest.raises(ValueError, match="comma"):
        parse_bracket_range("[1:2]")


def test_parse_reversed_closed_range_rejected() -> None:
    """Verify test parse reversed closed range rejected."""
    with pytest.raises(ValueError, match="start_line must be <="):
        parse_bracket_range("[15,3]")


def test_negative_and_zero_rejected() -> None:
    """Verify test negative and zero rejected."""
    with pytest.raises(ValueError, match=">= 1"):
        parse_bracket_range("[-1]")
    with pytest.raises(ValueError, match=">= 1"):
        parse_bracket_range("[1,-2]")
    with pytest.raises(ValueError, match=">= 1"):
        parse_bracket_range("[0,1]")


def test_parse_open_end_empty_file_rejected() -> None:
    """Verify test parse open end empty file rejected."""
    with pytest.raises(ValueError, match="empty file"):
        parse_bracket_range("[1:]", total_lines=0)


def test_overlapping_multi_ranges_rejected() -> None:
    """Verify test overlapping multi ranges rejected."""
    with pytest.raises(ValueError, match="Overlapping"):
        parse_bracket_ranges(["[1,2]", "[2,3]"], total_lines=10)


def test_non_overlapping_multi_ranges_ok() -> None:
    """Verify test non overlapping multi ranges ok."""
    rs = parse_bracket_ranges(["[1,2]", "[3,5]"], total_lines=10)
    assert rs == [LineRange(1, 2), LineRange(3, 5)]


def test_read_clamps_out_of_range_parse_result() -> None:
    """Verify test read clamps out of range parse result."""
    r = parse_bracket_range("[:99]", total_lines=None)
    assert r == LineRange(1, 99)
    assert clamp_read_range(r.start_line, r.end_line, 5) == (1, 5)


def test_write_strict_rejects_out_of_range_parsed() -> None:
    """Verify test write strict rejects out of range parsed."""
    r = parse_bracket_range("[1,50]")
    with pytest.raises(ValueError, match="bounds"):
        validate_range_against_length(
            r.start_line,
            r.end_line,
            total_lines=10,
            strict=True,
        )
