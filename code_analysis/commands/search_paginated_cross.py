"""
Paginated cross-search backend adapter (T-003/A-007).

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
from code_analysis.commands.project_cross_search_command import (
    ProjectCrossSearchCommand,
)

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


def normalize_cross_finding(
    raw: dict[str, Any],
    *,
    index: int,
    require_structural_grep: bool = True,
) -> Optional[dict[str, Any]]:
    """Map a cross-search row to a finding; return None for line-only grep rows when structural required."""
    evidence = raw.get("evidence") or {}
    source_mode = evidence.get("source_mode") or raw.get("source_mode") or ""
    if require_structural_grep and source_mode == "classic_line":
        return None
    return {
        "result_id": f"cross-{index:06d}",
        "source": "cross",
        "file_path": str(raw.get("file_path") or ""),
        "confidence": raw.get("confidence"),
        "score": raw.get("score"),
        "evidence": evidence if isinstance(evidence, dict) else {},
        "source_mode": source_mode,
    }


def _make_block_assembler(
    layout: SearchSessionDirectoryLayout,
    raw_config: dict[str, Any],
) -> BlockAssembler:
    policy = load_session_ttl_policy(raw_config)

    def _append_index(position: int, completeness: str) -> None:
        block_path = layout.blocks_dir / f"block_{position}.json"
        size = block_path.stat().st_size if block_path.is_file() else 0
        append_block_entry(
            layout.index_path,
            position=position,
            size_bytes=size,
            completeness=completeness,
        )

    def _update_metrics(metrics: dict[str, int]) -> None:
        def mutator(m: SearchSessionManifest) -> SearchSessionManifest:
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

    def _finalize() -> None:
        if layout.index_path.is_file():
            mark_index_finished(layout.index_path)
        else:
            atomic_write_json(
                layout.index_path, {"blocks": [], "completeness": COMPLETENESS_FINISHED}
            )

    return BlockAssembler(
        layout,
        RawFindingBuffer(layout.buffer_dir),
        policy.max_block_size_bytes,
        append_index_entry=_append_index,
        update_manifest_metrics=_update_metrics,
        finalize_index=_finalize,
    )


async def run_paginated_cross(
    *,
    command: ProjectCrossSearchCommand,
    params: dict[str, Any],
    session: SearchSession,
    layout: SearchSessionDirectoryLayout,
    raw_config: dict[str, Any],
    block_assembler_factory: Callable[..., BlockAssembler] = _make_block_assembler,
) -> Optional[int]:
    """Run legacy cross-search and publish first SearchResultBlock."""
    now = time.time()
    require_structural = bool(params.get("require_structural_grep", True))
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
    data = result.data or {}
    raw_list: list[dict[str, Any]] = []
    if isinstance(data.get("results"), list):
        raw_list = data["results"]
    elif isinstance(data.get("matches"), list):
        raw_list = data["matches"]
    buffer = RawFindingBuffer(layout.buffer_dir)
    idx = 0
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        finding = normalize_cross_finding(
            raw, index=idx, require_structural_grep=require_structural
        )
        if finding is not None:
            buffer.append_finding(f"cross-{idx:06d}", finding)
            idx += 1
    assembler = block_assembler_factory(layout, raw_config)
    assembler.run_until_idle(search_completed=True)
    return 1 if (layout.blocks_dir / "block_1.json").is_file() else None
