"""Tests for list pagination helpers."""

from __future__ import annotations

from code_analysis.core.list_pagination import (
    build_list_page_payload,
    resolve_list_pagination,
)


def test_resolve_list_pagination_defaults() -> None:
    """Verify test resolve list pagination defaults."""
    page_size, offset, block_position = resolve_list_pagination({})
    assert page_size == 20
    assert offset == 0
    assert block_position == 1


def test_resolve_list_pagination_block_position() -> None:
    """Verify test resolve list pagination block position."""
    page_size, offset, block_position = resolve_list_pagination(
        {"page_size": 10, "block_position": 3}
    )
    assert page_size == 10
    assert offset == 20
    assert block_position == 3


def test_build_list_page_payload_has_more() -> None:
    """Verify test build list page payload has more."""
    payload = build_list_page_payload(
        items=[{"id": 1}],
        total=3,
        page_size=1,
        block_position=1,
        offset=0,
        legacy_items_key="files",
    )
    assert payload["items"] == payload["files"]
    assert payload["has_more"] is True
    assert payload["paginated"] is True
    assert payload["total"] == 3
