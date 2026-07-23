"""
Paginated tree_query backend adapter (T-003/A-009).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Callable, Optional

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
from code_analysis.core.search_session.finding import (
    EXACT_STRUCTURAL_SCORE,
    Finding,
    FindingSource,
)
from code_analysis.core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    append_block_entry,
    mark_index_finished,
)
from code_analysis.core.search_session.service_metadata import (
    initialize_service_metadata,
)
from code_analysis.core.search_session.session import SearchSession


def normalize_tree_query_finding(
    raw: dict[str, Any], *, index: int
) -> Optional[Finding]:
    """Map a tree node match to a Finding; return None when no stable address."""
    stable_id = str(raw.get("stable_id") or raw.get("node_ref") or "")
    file_path = str(raw.get("file_path") or "")
    if not stable_id or not file_path:
        return None
    return Finding(
        result_id=f"tree_query-{index:06d}",
        source=FindingSource.tree_query,
        file_path=file_path,
        stable_id=stable_id,
        score=EXACT_STRUCTURAL_SCORE,
        content_stale=bool(raw.get("content_stale") or False),
    )


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


async def run_paginated_tree_query(
    *,
    params: dict[str, Any],
    session: SearchSession,
    layout: SearchSessionDirectoryLayout,
    raw_config: dict[str, Any],
    block_assembler_factory: Callable[..., BlockAssembler] = _make_block_assembler,
    tree_scanner: Callable[..., list[dict[str, Any]]],
) -> Optional[int]:
    """Run tree_query via injected scanner and publish first SearchResultBlock."""
    now = time.time()
    manifest = SearchSessionManifest(
        search_id=session.search_id,
        created_at=now,
        last_access_at=now,
        heartbeat_at=now,
        status="running",
        phase="xpath_filtering",
        request=params,
        metrics=dict(DEFAULT_METRICS),
        process=capture_server_process_identity(),
        block_ready_count=0,
    )
    write_manifest_atomic(layout, manifest)
    initialize_service_metadata(layout, now=now)
    raw_matches = tree_scanner(
        xpath=params.get("xpath", ""),
        file_pattern=params.get("file_pattern"),
        project_id=params.get("project_id"),
    )
    if not raw_matches:
        return None
    buffer = RawFindingBuffer(layout.buffer_dir)
    for i, raw in enumerate(raw_matches):
        if isinstance(raw, dict):
            finding = normalize_tree_query_finding(raw, index=i)
            if finding is not None:
                buffer.append_finding(f"tree_query-{i:06d}", finding.to_dict())
    assembler = block_assembler_factory(layout, raw_config)
    assembler.run_until_idle(search_completed=True)
    return 1 if (layout.blocks_dir / "block_1.json").is_file() else None
