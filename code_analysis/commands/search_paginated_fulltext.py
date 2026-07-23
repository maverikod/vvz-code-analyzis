"""
Pageinated fulltext search backend adapter (T-003/A-005).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Callable, Optional

from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.core.search_session.atomic_publication import atomic_write_json
from code_analysis.core.search_session.block_assembler import BlockAssembler
from code_analysis.core.search_session.directory import SearchSessionDirectoryLayout
from code_analysis.core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    capture_server_process_identity,
    update_manifest_atomic,
    write_manifest_atomic,
)
from code_analysis.core.search_session.policy import load_session_ttl_policy
from code_analysis.core.search_session.raw_finding_buffer import RawFindingBuffer
from code_analysis.core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    append_block_entry,
    mark_index_finished,
)
from code_analysis.core.search_session.service_metadata import (
    initialize_service_metadata,
)
from code_analysis.core.search_session.session import SearchSession
from code_analysis.commands.search_mcp_commands_fulltext import FulltextSearchMCPCommand

_STRIP_KEYS = frozenset(
    {
        "paginated",
        "include_job_id",
        "job_id",
        "block_position",
        "search_type",
        "page_size",
    }
)


def normalize_fulltext_finding(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    """Map a legacy fulltext result dict to a JSON-safe finding."""
    return {
        "result_id": f"fulltext-{index:06d}",
        "source": "fulltext",
        "file_path": str(raw.get("file_path") or ""),
        "line": raw.get("line") or raw.get("start_line"),
        "score": raw.get("bm25") or raw.get("rank"),
        "text": str(raw.get("chunk_text") or ""),
        "entity_type": raw.get("entity_type"),
        "entity_name": raw.get("entity_name"),
        "content_stale": bool(raw.get("content_stale") or False),
    }


def _make_block_assembler(
    layout: SearchSessionDirectoryLayout,
    raw_config: dict[str, Any],
) -> BlockAssembler:
    """Return make block assembler."""
    policy = load_session_ttl_policy(raw_config)

    def _append_index(position: int, completeness: str) -> None:
        """Return append index."""
        block_path = layout.blocks_dir / f"block_{position}.json"
        size = block_path.stat().st_size if block_path.is_file() else 0
        append_block_entry(
            layout.index_path,
            position=position,
            size_bytes=size,
            completeness=completeness,
        )

    def _update_metrics(metrics: dict[str, int]) -> None:
        """Return update metrics."""

        def mutator(m: SearchSessionManifest) -> SearchSessionManifest:
            """Return mutator."""
            nxt = dict(m.metrics)
            nxt["produced_results"] = nxt.get("produced_results", 0) + int(
                metrics.get("produced_results", 0)
            )
            nxt["written_blocks"] = nxt.get("written_blocks", 0) + int(
                metrics.get("written_blocks", 0)
            )
            return replace(
                m,
                metrics=nxt,
                block_ready_count=m.block_ready_count
                + int(metrics.get("written_blocks", 0)),
            )

        update_manifest_atomic(layout, mutator)

    return BlockAssembler(
        layout,
        RawFindingBuffer(layout.buffer_dir),
        policy.max_block_size_bytes,
        append_index_entry=_append_index,
        update_manifest_metrics=_update_metrics,
    )


async def run_paginated_fulltext(
    *,
    command: FulltextSearchMCPCommand,
    params: dict[str, Any],
    session: SearchSession,
    layout: SearchSessionDirectoryLayout,
    raw_config: dict[str, Any],
    block_assembler_factory: Callable[..., BlockAssembler] = _make_block_assembler,
) -> Optional[int]:
    """Run legacy fulltext execute and publish first SearchResultBlock."""
    now = time.time()
    backend_params = {k: v for k, v in params.items() if k not in _STRIP_KEYS}
    manifest = SearchSessionManifest(
        search_id=session.search_id,
        created_at=now,
        last_access_at=now,
        heartbeat_at=now,
        status="running",
        phase="indexed_search",
        request=backend_params,
        metrics=dict(DEFAULT_METRICS),
        process=capture_server_process_identity(),
        block_ready_count=0,
    )
    write_manifest_atomic(layout, manifest)
    initialize_service_metadata(layout, now=now)
    result = await command.execute(**backend_params)
    if isinstance(result, ErrorResult):
        raise RuntimeError(result.message)
    results = list((result.data or {}).get("results") or [])
    buffer = RawFindingBuffer(layout.buffer_dir)
    for i, raw in enumerate(results):
        if isinstance(raw, dict):
            buffer.append_finding(
                f"fulltext-{i:06d}", normalize_fulltext_finding(raw, index=i)
            )
    assembler = block_assembler_factory(layout, raw_config)
    assembler.run_until_idle(search_completed=True)
    return 1 if (layout.blocks_dir / "block_1.json").is_file() else None
