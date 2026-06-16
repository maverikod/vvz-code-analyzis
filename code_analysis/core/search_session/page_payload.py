"""
Build MCP page payloads for temporal (indexed-order) search result blocks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from typing import Any

from .directory import SearchSessionDirectoryLayout
from .manifest import read_manifest
from .result_block import block_items_from_payload
from .result_index import COMPLETENESS_RUNNING, read_index


def temporal_page_payload(
    *,
    layout: SearchSessionDirectoryLayout,
    job_id: str,
    block_position: int,
    search_still_running: bool,
) -> dict[str, Any]:
    """
    Assemble the same page slice shape as ``search_get_page`` (ordering=temporal).

    When the block file is missing, ``items`` is empty; ``has_more`` reflects
    whether more blocks may still arrive.
    """
    block_path = layout.blocks_dir / f"block_{block_position}.json"
    items: list[dict[str, Any]] = []
    if block_path.is_file():
        with open(block_path, encoding="utf-8") as fh:
            block_data = json.load(fh)
        items = block_items_from_payload(block_data)

    has_more = bool(search_still_running)
    if layout.index_path.is_file():
        index = read_index(layout.index_path)
        max_pos = max((e.get("position", 0) for e in index.blocks), default=0)
        if index.completeness == COMPLETENESS_RUNNING or block_position < max_pos:
            has_more = True

    manifest_obj = read_manifest(layout) if layout.manifest_path.is_file() else None
    if manifest_obj is not None:
        status = manifest_obj.status
        progress = dict(manifest_obj.metrics)
    else:
        status = "running" if search_still_running else "completed"
        progress = {}

    return {
        "job_id": job_id,
        "block_position": block_position,
        "ordering": "temporal",
        "items": items,
        "has_more": has_more,
        "status": status,
        "progress": progress,
        "warnings": [],
        "errors": [],
    }
