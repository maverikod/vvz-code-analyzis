"""
Shared offset pagination for list-style MCP commands (search-aligned response shape).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence, TypeVar

DEFAULT_LIST_PAGE_SIZE = 20
MAX_LIST_PAGE_SIZE = 200

T = TypeVar("T")


def list_pagination_schema_properties(
    *,
    include_limit_alias: bool = True,
) -> dict[str, dict[str, Any]]:
    """Schema fields shared by paginated list commands."""
    props: dict[str, dict[str, Any]] = {
        "page_size": {
            "type": "integer",
            "default": DEFAULT_LIST_PAGE_SIZE,
            "minimum": 1,
            "maximum": MAX_LIST_PAGE_SIZE,
            "description": (
                "Maximum rows per page (default 20). Same role as ``search`` "
                "``page_size`` / result block size."
            ),
        },
        "block_position": {
            "type": "integer",
            "default": 1,
            "minimum": 1,
            "description": (
                "1-based page index (default 1). Next page: increment "
                "``block_position``; same contract as ``search_get_page``."
            ),
        },
        "offset": {
            "type": "integer",
            "minimum": 0,
            "default": 0,
            "description": (
                "Legacy row offset. Ignored when ``block_position`` is set; "
                "otherwise equivalent to ``(block_position - 1) * page_size``."
            ),
        },
    }
    if include_limit_alias:
        props["limit"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LIST_PAGE_SIZE,
            "description": (
                "Legacy alias for ``page_size`` when ``page_size`` is omitted."
            ),
        }
    return props


def resolve_list_pagination(params: Mapping[str, Any]) -> tuple[int, int, int]:
    """
    Resolve ``page_size``, ``offset``, and ``block_position`` from request params.

    ``page_size`` defaults to 20. ``block_position`` defaults to 1 unless
    legacy ``offset`` is supplied without ``block_position``.
    """
    raw_page_size = params.get("page_size")
    if raw_page_size is None:
        raw_page_size = params.get("limit")
    if raw_page_size is None:
        page_size = DEFAULT_LIST_PAGE_SIZE
    else:
        page_size = max(1, min(int(raw_page_size), MAX_LIST_PAGE_SIZE))

    if params.get("block_position") is not None:
        block_position = max(1, int(params["block_position"]))
        offset = (block_position - 1) * page_size
    else:
        offset = max(0, int(params.get("offset") or 0))
        block_position = (offset // page_size) + 1 if page_size else 1

    return page_size, offset, block_position


def paginate_sequence(items: Sequence[T], *, offset: int, page_size: int) -> list[T]:
    """Return a slice ``items[offset : offset + page_size]``."""
    start = max(0, offset)
    end = start + page_size
    return list(items[start:end])


def build_list_page_payload(
    *,
    items: Sequence[Any],
    total: int,
    page_size: int,
    block_position: int,
    offset: int,
    legacy_items_key: str,
) -> dict[str, Any]:
    """
    Build a search-aligned page dict with canonical ``items`` plus legacy key.

    Args:
        items: Current page rows.
        total: Total rows before pagination.
        page_size: Resolved page size.
        block_position: 1-based page index.
        offset: Row offset used for this page.
        legacy_items_key: ``files`` or ``entities`` for backward compatibility.
    """
    page_items = list(items)
    consumed = offset + len(page_items)
    has_more = consumed < total
    payload: dict[str, Any] = {
        "success": True,
        "paginated": True,
        "items": page_items,
        legacy_items_key: page_items,
        "count": len(page_items),
        "total": total,
        "page_size": page_size,
        "block_position": block_position,
        "has_more": has_more,
        "offset": offset,
    }
    return payload


def apply_list_pagination_defaults(params: MutableMapping[str, Any]) -> None:
    """Normalize validated params in-place after schema merge."""
    page_size, offset, block_position = resolve_list_pagination(params)
    params["page_size"] = page_size
    params["offset"] = offset
    params["block_position"] = block_position


def apply_pagination_fields(
    payload: MutableMapping[str, Any],
    *,
    all_items: Sequence[Any],
    legacy_items_key: str,
    page_size: int,
    block_position: int,
    offset: int,
) -> dict[str, Any]:
    """Merge search-aligned pagination fields into an existing response dict."""
    page_items = paginate_sequence(all_items, offset=offset, page_size=page_size)
    total = len(all_items)
    consumed = offset + len(page_items)
    payload.update(
        {
            "paginated": True,
            "items": page_items,
            legacy_items_key: page_items,
            "count": len(page_items),
            "total": total,
            "page_size": page_size,
            "block_position": block_position,
            "has_more": consumed < total,
            "offset": offset,
        }
    )
    return dict(payload)
