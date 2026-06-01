"""
Paginated cross-search backend adapter (T-003/A-007).

Phase-based algorithm:
  Phase 1 (indexed) — semantic + fulltext in parallel, writes findings immediately.
  Phase 2 (grep/disk) — only index-gap files, supported extensions only, runs in
                         background task; findings written as each pattern finishes.
  search_start blocks until block_1 is ready or all phases complete, then returns.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import asyncio
import logging

import time
from dataclasses import replace
from typing import Any, Callable, List, Optional

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
from code_analysis.core.search_session.finding import (
    Finding,
    FindingSource,
    score_for_source,
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
from code_analysis.commands.project_cross_search_command import (
    ProjectCrossSearchCommand,
)
from code_analysis.commands.project_cross_search_core import (
    normalize_fulltext_hit,
    normalize_grep_hit,
    normalize_semantic_hit,
)
from code_analysis.commands.semantic_search_mcp import SemanticSearchMCPCommand
from code_analysis.core.index_coverage import IndexCoverageService
from code_analysis.core.structure_extraction.format_registry import (
    is_supported_extension,
)
from code_analysis.commands.search_mcp_commands_fulltext import FulltextSearchMCPCommand
from code_analysis.commands.fs_grep_command import FsGrepCommand

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
logger = logging.getLogger(__name__)

# Extensions considered worth grepping — avoids binary/generated files.
_SUPPORTED_EXTENSIONS = frozenset(
    {
        ".py",
        ".md",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".txt",
        ".rst",
        ".cfg",
        ".ini",
        ".sh",
        ".js",
        ".ts",
        ".sql",
    }
)


def normalize_cross_finding(
    raw: dict[str, Any],
    *,
    index: int,
    require_structural_grep: bool = True,
) -> Optional[Finding]:
    """Map a cross-search row to a Finding; return None for line-only or unaddressable rows."""
    evidence = raw.get("evidence") or {}
    source_mode = evidence.get("source_mode") or raw.get("source_mode") or ""
    if require_structural_grep and source_mode == "classic_line":
        return None
    stable_id = (
        evidence.get("node_ref")
        or raw.get("node_ref")
        or evidence.get("block_id")
        or raw.get("block_id")
        or ""
    )
    if not stable_id:
        return None
    return Finding(
        result_id=f"cross-{index:06d}",
        source=FindingSource.cross,
        file_path=str(raw.get("file_path") or ""),
        stable_id=str(stable_id),
        score=score_for_source(FindingSource.cross, raw),
    )


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

    return BlockAssembler(
        layout,
        RawFindingBuffer(layout.buffer_dir),
        policy.max_block_size_bytes,
        append_index_entry=_append_index,
        update_manifest_metrics=_update_metrics,
    )


def _prefilter_candidates(
    command: ProjectCrossSearchCommand,
    project_id: str,
    log: logging.Logger,
) -> tuple[List[str], List[str]]:
    """
    Build the candidate file list and split it into indexed vs index-gap.

    Step 1: walk the project root, keep only supported extensions (skips
    binary/generated files). Step 2: classify each candidate with
    IndexCoverageService — index_gap_paths need disk grep, indexed_paths are
    already covered by the semantic/fulltext DB search.

    Returns (indexed_paths, index_gap_paths), both project-relative POSIX.
    Never raises: on any failure returns empty lists so the caller can fall
    back to unrestricted search.
    """
    t_pf = time.monotonic()
    try:
        project_root = command._resolve_project_root(project_id).resolve()
    except Exception as exc:
        log.warning("[TIMING] prefilter: cannot resolve project root: %s", exc)
        return [], []

    candidates: List[str] = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(project_root).as_posix()
        guard = f"/{rel}"
        if rel.startswith(".") or "/." in guard:
            continue
        if "/venv/" in guard or "__pycache__" in rel:
            continue
        if "/node_modules/" in guard:
            continue
        if is_supported_extension(rel):
            candidates.append(rel)

    t_walk = time.monotonic()
    database = None
    indexed_paths: List[str] = []
    index_gap_paths: List[str] = []
    try:
        database = command._open_database_from_config(auto_analyze=False)
        coverage = IndexCoverageService(database, project_id, project_root)
        index_gap_paths, _reasons = coverage.filter_grep_candidates_with_reasons(
            candidates,
            skip_indexed_unchanged=True,
            indexed_only=False,
        )
        gap_set = set(index_gap_paths)
        indexed_paths = [rel for rel in candidates if rel not in gap_set]
    except Exception as exc:
        log.warning("[TIMING] prefilter: coverage classification failed: %s", exc)
        return [], []
    finally:
        if database is not None:
            database.disconnect()

    log.info(
        "[TIMING] prefilter: candidates=%d indexed=%d index_gap=%d "
        "walk=%.3fs classify=%.3fs total=%.3fs",
        len(candidates),
        len(indexed_paths),
        len(index_gap_paths),
        t_walk - t_pf,
        time.monotonic() - t_walk,
        time.monotonic() - t_pf,
    )
    return indexed_paths, index_gap_paths


async def run_paginated_cross(
    *,
    command: ProjectCrossSearchCommand,
    params: dict[str, Any],
    session: SearchSession,
    layout: SearchSessionDirectoryLayout,
    raw_config: dict[str, Any],
    block_assembler_factory: Callable[..., BlockAssembler] = _make_block_assembler,
) -> Optional[int]:
    """
    Phase-based paginated cross-search.

    Phase 1 (indexed): semantic + fulltext run in parallel against the DB.
    Findings are written to the buffer immediately after each source completes.
    Assembler is flushed — first block(s) become available to the client.

    Phase 2 (grep/disk): only files not yet indexed (index_gap), only
    supported extensions. Each pattern's results are written and flushed
    as they arrive. Runs as an asyncio background task.

    search_start waits until block_1 exists or all phases complete.
    """
    t0 = time.monotonic()
    log = logger.getChild(session.search_id[:8])
    log.info("[TIMING] run_paginated_cross start")

    project_id = str(params.get("project_id", ""))
    query = str(params.get("query", ""))
    require_structural = bool(params.get("require_structural_grep", True))
    semantic_limit = int(params.get("semantic_limit", 30))
    fulltext_limit = int(params.get("fulltext_limit", 30))
    grep_patterns: List[str] = list(params.get("grep_patterns") or [])
    if not grep_patterns and query:
        grep_patterns = [query]
    hard_timeout = float(params.get("hard_timeout_seconds", 120.0))
    min_score = float(params.get("min_semantic_score", 0.45))

    now = time.time()
    backend_params = {k: v for k, v in params.items() if k not in _STRIP_KEYS}
    backend_params["auto_queue_on_inline_timeout"] = False
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

    buffer = RawFindingBuffer(layout.buffer_dir)
    max_block_size_bytes = load_session_ttl_policy(raw_config).max_block_size_bytes
    assembler = block_assembler_factory(layout, max_block_size_bytes)
    idx = 0

    def _flush(search_completed: bool = False) -> None:
        assembler.run_until_idle(search_completed=search_completed)

    def _write_findings(raw_list: list[dict[str, Any]], prefix: str) -> int:
        nonlocal idx
        written = 0
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            finding = normalize_cross_finding(
                raw,
                index=idx,
                require_structural_grep=require_structural,
            )
            if finding is not None:
                buffer.append_finding(f"{prefix}-{idx:06d}", finding.to_dict())
                idx += 1
                written += 1
        return written

    indexed_paths, index_gap_paths = _prefilter_candidates(command, project_id, log)
    log.info(
        "[TIMING] prefilter result: indexed=%d index_gap=%d",
        len(indexed_paths),
        len(index_gap_paths),
    )

    # ------------------------------------------------------------------ #
    # Phase 1: indexed (semantic + fulltext) in parallel                  #
    # ------------------------------------------------------------------ #
    log.info("[TIMING] phase1_indexed start")

    async def _run_semantic() -> List[dict[str, Any]]:
        if semantic_limit <= 0:
            return []
        try:
            sem_cmd = SemanticSearchMCPCommand()
            result = await sem_cmd.execute(
                project_id=project_id,
                query=query,
                limit=min(semantic_limit, 100),
                min_score=min_score,
            )
            if isinstance(result, ErrorResult):
                log.warning("[TIMING] semantic error: %s", result)
                return []
            return list((result.data or {}).get("results") or [])
        except Exception as exc:
            log.warning("[TIMING] semantic exception: %s", exc)
            return []

    async def _run_fulltext() -> List[dict[str, Any]]:
        if fulltext_limit <= 0:
            return []
        try:
            ft_cmd = FulltextSearchMCPCommand()
            result = await ft_cmd.execute(
                project_id=project_id,
                query=query,
                limit=fulltext_limit,
            )
            if isinstance(result, ErrorResult):
                log.warning("[TIMING] fulltext error: %s", result)
                return []
            return list((result.data or {}).get("results") or [])
        except Exception as exc:
            log.warning("[TIMING] fulltext exception: %s", exc)
            return []

    t_p1 = time.monotonic()
    sem_rows, ft_rows = await asyncio.gather(_run_semantic(), _run_fulltext())
    t_p1_done = time.monotonic()
    log.info(
        "[TIMING] phase1_indexed done: semantic=%d fulltext=%d elapsed=%.3fs",
        len(sem_rows),
        len(ft_rows),
        t_p1_done - t_p1,
    )

    # Write phase-1 findings to buffer and flush immediately.
    n_sem = _write_findings(sem_rows, "sem")
    n_ft = _write_findings(ft_rows, "ft")
    log.info(
        "[TIMING] phase1_written: sem=%d ft=%d; flushing...",
        n_sem,
        n_ft,
    )
    _flush(search_completed=False)
    log.info(
        "[TIMING] phase1_flushed elapsed=%.3fs blocks=%s",
        time.monotonic() - t0,
        (layout.blocks_dir / "block_1.json").is_file(),
    )

    # ------------------------------------------------------------------ #
    # Phase 2: grep on disk (index_gap, supported extensions only)        #
    # ------------------------------------------------------------------ #
    async def _run_grep_phase() -> None:
        if not grep_patterns:
            log.info("[TIMING] phase2_grep skipped: no patterns")
            _flush(search_completed=True)
            return

        log.info("[TIMING] phase2_grep start patterns=%d", len(grep_patterns))
        t_g = time.monotonic()
        grep_cmd = FsGrepCommand()
        for i, pattern in enumerate(grep_patterns):
            t_pat = time.monotonic()
            try:
                result = await grep_cmd.execute(
                    project_id=project_id,
                    pattern=pattern,
                    literal=bool(params.get("literal", True)),
                    case_sensitive=bool(params.get("case_sensitive", False)),
                    skip_indexed_unchanged=True,  # index_gap only
                    fast_text_only=False,
                    enrich_blocks=True,
                    enrich_max_results=50,
                    ensure_persisted_tree=True,
                    stable_ids_required=True,
                    hard_timeout_seconds=max(
                        5.0, hard_timeout - (time.monotonic() - t_g)
                    ),
                    auto_queue_on_inline_timeout=False,
                )
            except Exception as exc:
                log.warning("[TIMING] phase2 pattern[%d] exception: %s", i, exc)
                continue

            if isinstance(result, ErrorResult):
                log.warning("[TIMING] phase2 pattern[%d] error: %s", i, result)
                continue

            matches = list((result.data or {}).get("matches") or [])
            # Filter by supported extensions.
            filtered = [
                m
                for m in matches
                if not m.get("file_path")
                or any(
                    str(m["file_path"]).endswith(ext) for ext in _SUPPORTED_EXTENSIONS
                )
            ]
            n_grep = _write_findings(filtered, f"grep{i}")
            _flush(search_completed=False)
            log.info(
                "[TIMING] phase2 pattern[%d]=%r matches=%d written=%d elapsed=%.3fs",
                i,
                pattern,
                len(filtered),
                n_grep,
                time.monotonic() - t_pat,
            )
            if time.monotonic() - t_g >= hard_timeout:
                log.warning("[TIMING] phase2_grep hard timeout reached")
                break

        log.info(
            "[TIMING] phase2_grep done total_elapsed=%.3fs",
            time.monotonic() - t_g,
        )
        _flush(search_completed=True)

    # Launch grep as background task; return as soon as block_1 exists.
    grep_task = asyncio.ensure_future(_run_grep_phase())
    try:
        # Poll until block_1 is published or grep is done.
        poll_start = time.monotonic()
        while not (layout.blocks_dir / "block_1.json").is_file():
            if grep_task.done():
                break
            if time.monotonic() - poll_start > hard_timeout:
                log.warning("[TIMING] poll timeout waiting for block_1")
                break
            await asyncio.sleep(0.05)
        # Wait for grep to finish (it may already be done).
        await grep_task
    except Exception as exc:
        log.warning("[TIMING] grep_task error: %s", exc)

    total = time.monotonic() - t0
    block1_ready = (layout.blocks_dir / "block_1.json").is_file()
    log.info(
        "[TIMING] run_paginated_cross done total=%.3fs block1=%s findings=%d",
        total,
        block1_ready,
        idx,
    )
    return 1 if block1_ready else None
