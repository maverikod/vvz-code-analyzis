"""
Framework-agnostic HTTP handlers for search job result access.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_analysis.core.search_session.directory import (
    BLOCKS_DIRNAME,
    BUFFER_DIRNAME,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    RELEVANCE_BLOCKS_DIRNAME,
    SERVICE_METADATA_FILENAME,
    SearchSessionDirectoryLayout,
)
from code_analysis.core.search_session.manifest import read_manifest
from code_analysis.core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    COMPLETENESS_RUNNING,
    read_index,
)
from code_analysis.core.search_session.service_metadata import (
    initialize_service_metadata,
    refresh_last_access,
)
from code_analysis.core.search_session.status import snapshot_from_manifest

BLOCK_NOT_READY = "BLOCK_NOT_READY"
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
BLOCK_NOT_FOUND = "BLOCK_NOT_FOUND"


@dataclass(frozen=True)
class HttpAccessContext:
    """Dependencies required by search job HTTP handlers."""

    sessions_root: Path


def resolve_session_layout(
    ctx: HttpAccessContext,
    job_id: str,
) -> SearchSessionDirectoryLayout:
    """Resolve on-disk layout for ``job_id`` under the configured sessions root."""
    root = ctx.sessions_root.resolve() / job_id
    return SearchSessionDirectoryLayout(
        root=root,
        manifest_path=root / MANIFEST_FILENAME,
        index_path=root / INDEX_FILENAME,
        service_metadata_path=root / SERVICE_METADATA_FILENAME,
        blocks_dir=root / BLOCKS_DIRNAME,
        relevance_blocks_dir=root / RELEVANCE_BLOCKS_DIRNAME,
        buffer_dir=root / BUFFER_DIRNAME,
    )


def _session_exists(layout: SearchSessionDirectoryLayout) -> bool:
    return bool(layout.root.is_dir())


def _refresh_access(layout: SearchSessionDirectoryLayout) -> None:
    now = time.time()
    if layout.service_metadata_path.is_file():
        refresh_last_access(layout, now=now)
    else:
        initialize_service_metadata(layout, now=now)


def _not_found(code: str, message: str) -> tuple[int, dict[str, Any]]:
    return 404, {"error": {"code": code, "message": message}}


def _conflict(code: str, message: str) -> tuple[int, dict[str, Any]]:
    return 409, {"error": {"code": code, "message": message}}


def handle_get_index(
    ctx: HttpAccessContext,
    job_id: str,
) -> tuple[int, dict[str, Any]]:
    """Return the search result index JSON and refresh last access."""
    layout = resolve_session_layout(ctx, job_id)
    if not _session_exists(layout):
        return _not_found(SESSION_NOT_FOUND, f"Search session not found: {job_id}")

    if layout.index_path.is_file():
        index = read_index(layout.index_path)
        payload = {
            "blocks": list(index.blocks),
            "completeness": index.completeness,
        }
    else:
        payload = {
            "blocks": [],
            "completeness": COMPLETENESS_RUNNING,
        }

    _refresh_access(layout)
    return 200, payload


def handle_get_block(
    ctx: HttpAccessContext,
    job_id: str,
    position: int,
) -> tuple[int, dict[str, Any]]:
    """Return one published block by position or a block-not-ready response."""
    layout = resolve_session_layout(ctx, job_id)
    if not _session_exists(layout):
        return _not_found(SESSION_NOT_FOUND, f"Search session not found: {job_id}")

    if layout.index_path.is_file():
        index = read_index(layout.index_path)
    else:
        index = None
    indexed_positions: set[int] = set()
    completeness = COMPLETENESS_RUNNING
    if index is not None:
        indexed_positions = {
            int(entry["position"]) for entry in index.blocks if "position" in entry
        }
        completeness = index.completeness
    block_path = layout.blocks_dir / f"block_{position}.json"

    if position not in indexed_positions:
        if completeness == COMPLETENESS_RUNNING:
            return _conflict(
                BLOCK_NOT_READY,
                f"Block {position} is not published yet for job {job_id}",
            )
        return _not_found(
            BLOCK_NOT_FOUND,
            f"Block {position} not found for job {job_id}",
        )

    if not block_path.is_file():
        if completeness == COMPLETENESS_RUNNING:
            return _conflict(
                BLOCK_NOT_READY,
                f"Block {position} is not published yet for job {job_id}",
            )
        return _not_found(
            BLOCK_NOT_FOUND,
            f"Block {position} not found for job {job_id}",
        )

    with open(block_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    _refresh_access(layout)
    if isinstance(payload, dict):
        return 200, payload
    return 200, {"block": payload}


def handle_get_status(
    ctx: HttpAccessContext,
    job_id: str,
) -> tuple[int, dict[str, Any]]:
    """Return manifest status, phase, and metrics; refresh last access."""
    layout = resolve_session_layout(ctx, job_id)
    if not _session_exists(layout):
        return _not_found(SESSION_NOT_FOUND, f"Search session not found: {job_id}")

    if not layout.manifest_path.is_file():
        return _not_found(SESSION_NOT_FOUND, f"Search manifest not found: {job_id}")

    manifest = read_manifest(layout)
    snapshot = snapshot_from_manifest(manifest)
    _refresh_access(layout)
    return 200, {
        "search_id": manifest.search_id,
        "status": snapshot.status,
        "phase": snapshot.phase.value,
        "block_not_ready": snapshot.block_not_ready,
        "message": snapshot.message,
        "metrics": dict(manifest.metrics),
        "block_ready_count": manifest.block_ready_count,
    }
