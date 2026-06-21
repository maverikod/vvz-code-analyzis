"""
Paginated cross-search backend adapter (T-003/A-007).

Phase-based algorithm:
    Phase 1 — fulltext (always), flush first block as soon as possible.
    Phase 2 — semantic when enable_semantic (optional).
    Phase 3 — grep on disk when enable_grep (optional).
    Phases 2 and 3 run in parallel after phase 1. The ``search`` command returns
    after block_1; remaining phases run in a dedicated background thread.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import asyncio
import logging

import time
from dataclasses import replace
from typing import Any, Callable, List, Literal, Optional

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
from code_analysis.core.search_session.search_profile_log import (
    SearchProfileRecorder,
    open_search_profile_recorder,
    request_summary_fields,
)
from code_analysis.core.search_session.session import SearchSession
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_cross_search_command import (
    ProjectCrossSearchCommand,
)
from code_analysis.commands.project_cross_search_core import (
    is_structural_grep_evidence,
    normalize_grep_hit,
)
from code_analysis.commands.search_paginated_fulltext import normalize_fulltext_finding
from code_analysis.commands.search_paginated_semantic import normalize_semantic_finding
from code_analysis.commands.semantic_search_mcp import SemanticSearchMCPCommand
from code_analysis.core.index_coverage import IndexCoverageService
from code_analysis.core.structure_extraction.format_registry import (
    is_supported_extension,
)
from code_analysis.commands.search_mcp_commands_fulltext import FulltextSearchMCPCommand
from code_analysis.commands.fs_grep_command import FsGrepCommand
from code_analysis.commands.file_management.relative_path_list_pattern import (
    relative_path_matches_listing_pattern,
)

_STRIP_KEYS = frozenset(
    {
        "paginated",
        "include_job_id",
        "job_id",
        "block_position",
        "search_type",
        "page_size",
        "first_block_wait_seconds",
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


_IndexedSource = Literal["fulltext", "semantic"]


def indexed_finding_payload(
    raw: dict[str, Any],
    *,
    index: int,
    source: _IndexedSource,
) -> dict[str, Any]:
    """Map phase-1 fulltext/semantic rows to buffer dicts (same shape as paginated FTS/sem)."""
    if source == "fulltext":
        payload = normalize_fulltext_finding(raw, index=index)
        text = raw.get("chunk_text") or raw.get("content")
        if text and not payload.get("text"):
            payload = {**payload, "text": str(text)}
        score = raw.get("bm25_score")
        if score is not None and payload.get("score") is None:
            payload = {**payload, "score": score}
        return payload
    payload = normalize_semantic_finding(raw, index=index)
    text = raw.get("chunk_text") or raw.get("text")
    if text and not payload.get("text"):
        payload = {**payload, "text": str(text)}
    return payload


def grep_finding_payload(
    raw: dict[str, Any],
    *,
    index: int,
    pattern: str,
    project_root: Optional[Any],
    require_structural_grep: bool,
) -> Optional[dict[str, Any]]:
    """Map phase-2 grep match to a buffer dict; structural rows prefer node_ref/block_id."""
    norm = normalize_grep_hit(raw, pattern, project_root)
    merged = {**norm, **{k: v for k, v in raw.items() if k not in norm}}
    if require_structural_grep and not is_structural_grep_evidence(merged):
        return None
    cross_row = normalize_cross_finding(
        {
            "file_path": norm.get("file_path"),
            "score": norm.get("score"),
            "evidence": {
                "source_mode": merged.get("source_mode")
                or (merged.get("metadata") or {}).get("grep_source"),
                "node_ref": (merged.get("metadata") or {}).get("node_ref")
                or merged.get("node_ref"),
                "block_id": (merged.get("metadata") or {}).get("block_id")
                or merged.get("block_id"),
            },
        },
        index=index,
        require_structural_grep=require_structural_grep,
    )
    if cross_row is not None:
        return cross_row.to_dict()
    if require_structural_grep:
        return None
    line = norm.get("line_start") or 0
    file_path = str(norm.get("file_path") or "")
    return {
        "result_id": f"grep-{index:06d}",
        "source": FindingSource.grep.value,
        "file_path": file_path,
        "stable_id": f"grep:{file_path}:{line}",
        "score": score_for_source(FindingSource.grep.value, merged),
        "line": line,
        "text": norm.get("text"),
        "entity_type": norm.get("entity_type"),
    }


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
    max_block_size_bytes: int,
    max_results_per_block: int | None = None,
    *,
    on_block_published: Callable[[int, int, int], None] | None = None,
) -> BlockAssembler:
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
        max_block_size_bytes,
        max_results_per_block=max_results_per_block,
        append_index_entry=_append_index,
        update_manifest_metrics=_update_metrics,
        on_block_published=on_block_published,
    )


def _prefilter_candidates(
    command: ProjectCrossSearchCommand,
    project_id: str,
    log: logging.Logger,
    profile: SearchProfileRecorder | None = None,
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
    if profile is not None:
        profile.checkpoint("prefilter_start", project_id=project_id)
    try:
        project_root = command._resolve_project_root(project_id).resolve()
    except Exception as exc:
        log.warning("[TIMING] prefilter: cannot resolve project root: %s", exc)
        if profile is not None:
            profile.checkpoint("prefilter_error", stage="resolve_root", error=str(exc))
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
    if profile is not None:
        profile.checkpoint(
            "prefilter_walk_done",
            candidates=len(candidates),
            walk_sec=round(t_walk - t_pf, 4),
        )
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
        if profile is not None:
            profile.checkpoint("prefilter_error", stage="classify", error=str(exc))
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
    if profile is not None:
        profile.checkpoint(
            "prefilter_done",
            candidates=len(candidates),
            indexed=len(indexed_paths),
            index_gap=len(index_gap_paths),
            total_sec=round(time.monotonic() - t_pf, 4),
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

    Phase 2 (grep/disk): fs_grep with skip_indexed_unchanged. Each pattern's
    results are written and flushed as they arrive.

    search_start waits until block_1 exists or all phases complete.
    """
    t0 = time.monotonic()
    log = logger.getChild(session.search_id[:8])
    log.info("[TIMING] run_paginated_cross start")
    config_path = BaseMCPCommand._resolve_config_path()
    profile = open_search_profile_recorder(
        job_id=session.search_id,
        raw_config=raw_config,
        config_path=config_path,
    )
    profile.checkpoint("cross_run_start", **request_summary_fields(params))

    project_id = str(params.get("project_id", ""))
    query = str(params.get("query", ""))
    enable_semantic = bool(params.get("enable_semantic", True))
    enable_grep = bool(params.get("enable_grep", False))
    require_structural = bool(params.get("require_structural_grep", True))
    semantic_limit = int(params.get("semantic_limit", 30)) if enable_semantic else 0
    fulltext_limit = int(params.get("fulltext_limit", 30))
    grep_patterns: List[str] = (
        list(params.get("grep_patterns") or []) if enable_grep else []
    )
    if enable_grep and not grep_patterns and query:
        grep_patterns = [query]
    hard_timeout = float(params.get("hard_timeout_seconds", 120.0))
    min_score = float(params.get("min_semantic_score", 0.45))
    file_pattern = str(params.get("file_pattern") or "").strip()

    def _path_matches_filter(file_path: str) -> bool:
        if not file_pattern:
            return True
        rel = str(file_path or "").replace("\\", "/").lstrip("./")
        return relative_path_matches_listing_pattern(rel, file_pattern)

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
    profile.checkpoint("cross_manifest_written")

    buffer = RawFindingBuffer(layout.buffer_dir)
    max_block_size_bytes = load_session_ttl_policy(raw_config).max_block_size_bytes
    page_size_raw = params.get("page_size", 20)
    max_results_per_block = int(page_size_raw) if page_size_raw is not None else None
    if max_results_per_block is not None and max_results_per_block < 1:
        max_results_per_block = None

    def _on_block_published(position: int, item_count: int, size_bytes: int) -> None:
        profile.checkpoint(
            "assembler_block_published",
            block_position=position,
            items=item_count,
            size_bytes=size_bytes,
        )

    assembler = block_assembler_factory(
        layout,
        max_block_size_bytes,
        max_results_per_block,
        on_block_published=_on_block_published,
    )
    idx = 0

    def _flush(search_completed: bool = False) -> None:
        buffer_bytes = buffer.total_bytes()
        t_flush = time.monotonic()
        published = assembler.run_until_idle(search_completed=search_completed)
        profile.checkpoint(
            "block_flush",
            search_completed=search_completed,
            blocks_published=published,
            buffer_bytes_before=buffer_bytes,
            flush_sec=round(time.monotonic() - t_flush, 4),
            block1_exists=(layout.blocks_dir / "block_1.json").is_file(),
        )
        if search_completed and published == 0 and buffer_bytes == 0:
            profile.checkpoint("assembler_finalize", relevance=True)

    project_root: Optional[Any] = None
    try:
        project_root = command._resolve_project_root(project_id).resolve()
    except Exception as exc:
        log.warning("[TIMING] cannot resolve project root for grep normalize: %s", exc)

    def _write_indexed_findings(
        raw_list: list[dict[str, Any]],
        prefix: str,
        source: _IndexedSource,
    ) -> int:
        nonlocal idx
        written = 0
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            payload = indexed_finding_payload(raw, index=idx, source=source)
            buffer.append_finding(f"{prefix}-{idx:06d}", payload)
            idx += 1
            written += 1
        return written

    def _write_grep_findings(
        raw_list: list[dict[str, Any]],
        prefix: str,
        pattern: str,
    ) -> int:
        nonlocal idx
        written = 0
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            payload = grep_finding_payload(
                raw,
                index=idx,
                pattern=pattern,
                project_root=project_root,
                require_structural_grep=require_structural,
            )
            if payload is None:
                continue
            buffer.append_finding(f"{prefix}-{idx:06d}", payload)
            idx += 1
            written += 1
        return written

    async def _run_semantic() -> List[dict[str, Any]]:
        if semantic_limit <= 0:
            return []
        profile.checkpoint("semantic_backend_start", limit=min(semantic_limit, 100))
        t_be = time.monotonic()
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
                profile.checkpoint(
                    "semantic_backend_error",
                    backend_sec=round(time.monotonic() - t_be, 4),
                    error=str(result),
                )
                return []
            rows = list((result.data or {}).get("results") or [])
            if file_pattern:
                rows = [
                    r
                    for r in rows
                    if isinstance(r, dict)
                    and _path_matches_filter(
                        str(r.get("file_path") or r.get("path") or "")
                    )
                ]
            profile.checkpoint(
                "semantic_backend_done",
                backend_sec=round(time.monotonic() - t_be, 4),
                rows=len(rows),
            )
            return rows
        except Exception as exc:
            log.warning("[TIMING] semantic exception: %s", exc)
            profile.checkpoint(
                "semantic_backend_error",
                backend_sec=round(time.monotonic() - t_be, 4),
                error=str(exc),
            )
            return []

    async def _run_fulltext() -> List[dict[str, Any]]:
        if fulltext_limit <= 0:
            return []
        profile.checkpoint("fulltext_backend_start", limit=fulltext_limit)
        t_be = time.monotonic()
        try:
            ft_cmd = FulltextSearchMCPCommand()
            result = await ft_cmd.execute(
                project_id=project_id,
                query=query,
                limit=fulltext_limit,
            )
            if isinstance(result, ErrorResult):
                log.warning("[TIMING] fulltext error: %s", result)
                profile.checkpoint(
                    "fulltext_backend_error",
                    backend_sec=round(time.monotonic() - t_be, 4),
                    error=str(result),
                )
                return []
            rows = list((result.data or {}).get("results") or [])
            if file_pattern:
                rows = [
                    r
                    for r in rows
                    if isinstance(r, dict)
                    and _path_matches_filter(
                        str(r.get("file_path") or r.get("path") or "")
                    )
                ]
            profile.checkpoint(
                "fulltext_backend_done",
                backend_sec=round(time.monotonic() - t_be, 4),
                rows=len(rows),
            )
            return rows
        except Exception as exc:
            log.warning("[TIMING] fulltext exception: %s", exc)
            profile.checkpoint(
                "fulltext_backend_error",
                backend_sec=round(time.monotonic() - t_be, 4),
                error=str(exc),
            )
            return []

    async def _run_grep_phase() -> None:
        if not grep_patterns:
            log.info("[TIMING] phase3_grep skipped: no patterns")
            profile.checkpoint("grep_phase_skipped", reason="no_patterns")
            _flush(search_completed=True)
            return

        update_manifest_atomic(
            layout,
            lambda m: replace(m, phase="dynamic_discovery"),
        )
        log.info("[TIMING] phase3_grep start patterns=%d", len(grep_patterns))
        profile.checkpoint("grep_phase_start", patterns=len(grep_patterns))
        t_g = time.monotonic()
        grep_cmd = FsGrepCommand()
        for i, pattern in enumerate(grep_patterns):
            t_pat = time.monotonic()
            profile.checkpoint(
                "grep_pattern_start",
                pattern_index=i,
                pattern_len=len(pattern),
            )
            batches_flushed = 0

            def _on_grep_batch(
                batch: list[dict[str, Any]],
                *,
                pattern_index: int = i,
                grep_pattern: str = pattern,
            ) -> None:
                nonlocal batches_flushed
                filtered = [
                    m
                    for m in batch
                    if not (m.get("file_path") or m.get("relative_path"))
                    or any(
                        str(
                            m.get("file_path") or m.get("relative_path") or ""
                        ).endswith(ext)
                        for ext in _SUPPORTED_EXTENSIONS
                    )
                ]
                n_grep = _write_grep_findings(
                    filtered, f"grep{pattern_index}", grep_pattern
                )
                if n_grep <= 0:
                    return
                batches_flushed += 1
                _flush(search_completed=False)
                profile.checkpoint(
                    "grep_batch_flushed",
                    pattern_index=pattern_index,
                    batch_matches=len(filtered),
                    written=n_grep,
                    flush_count=batches_flushed,
                )
                log.info(
                    "[TIMING] phase3 grep batch pattern[%d] written=%d flush=%d",
                    pattern_index,
                    n_grep,
                    batches_flushed,
                )

            try:
                result = await grep_cmd.execute(
                    project_id=project_id,
                    pattern=pattern,
                    file_pattern=file_pattern or None,
                    literal=bool(params.get("literal", True)),
                    case_sensitive=bool(params.get("case_sensitive", False)),
                    skip_indexed_unchanged=True,
                    fast_text_only=False,
                    enrich_blocks=True,
                    enrich_max_results=50,
                    ensure_persisted_tree=True,
                    stable_ids_required=True,
                    hard_timeout_seconds=max(
                        5.0, hard_timeout - (time.monotonic() - t_g)
                    ),
                    auto_queue_on_inline_timeout=False,
                    on_match_batch=_on_grep_batch,
                )
            except Exception as exc:
                log.warning("[TIMING] phase3 pattern[%d] exception: %s", i, exc)
                profile.checkpoint(
                    "grep_pattern_error",
                    pattern_index=i,
                    error=str(exc),
                    pattern_sec=round(time.monotonic() - t_pat, 4),
                )
                continue

            if isinstance(result, ErrorResult):
                log.warning("[TIMING] phase3 pattern[%d] error: %s", i, result)
                profile.checkpoint(
                    "grep_pattern_error",
                    pattern_index=i,
                    error=str(result),
                    pattern_sec=round(time.monotonic() - t_pat, 4),
                )
                continue

            profile.checkpoint(
                "grep_pattern_done",
                pattern_index=i,
                batches_flushed=batches_flushed,
                pattern_sec=round(time.monotonic() - t_pat, 4),
            )
            log.info(
                "[TIMING] phase3 pattern[%d]=%r batches_flushed=%d elapsed=%.3fs",
                i,
                pattern,
                batches_flushed,
                time.monotonic() - t_pat,
            )
            if time.monotonic() - t_g >= hard_timeout:
                log.warning("[TIMING] phase3_grep hard timeout reached")
                break

            if time.monotonic() - t_g >= hard_timeout:
                log.warning("[TIMING] phase3_grep hard timeout reached")
                profile.checkpoint("grep_phase_timeout")
                break

        log.info(
            "[TIMING] phase3_grep done total_elapsed=%.3fs",
            time.monotonic() - t_g,
        )
        profile.checkpoint(
            "grep_phase_done",
            total_sec=round(time.monotonic() - t_g, 4),
        )
        _flush(search_completed=True)

    async def _run_semantic_phase() -> None:
        if not (enable_semantic and semantic_limit > 0):
            return
        log.info("[TIMING] phase2_semantic start")
        profile.checkpoint("phase2_semantic_start")
        t_sem = time.monotonic()
        sem_rows = await _run_semantic()
        n_sem = _write_indexed_findings(sem_rows, "sem", "semantic")
        profile.checkpoint("phase2_semantic_buffered", findings=n_sem)
        _flush(search_completed=False)
        log.info(
            "[TIMING] phase2_semantic done: semantic=%d elapsed=%.3fs",
            n_sem,
            time.monotonic() - t_sem,
        )
        profile.checkpoint(
            "phase2_semantic_done",
            findings=n_sem,
            phase_sec=round(time.monotonic() - t_sem, 4),
        )
        update_manifest_atomic(
            layout,
            lambda m: replace(m, phase="indexed_search"),
        )

    # ------------------------------------------------------------------ #
    # Phase 1: fulltext (always) — first block for the caller            #
    # ------------------------------------------------------------------ #
    log.info("[TIMING] phase1_fulltext start")
    profile.checkpoint("phase1_fulltext_start")
    t_p1 = time.monotonic()
    ft_rows = await _run_fulltext()
    n_ft = _write_indexed_findings(ft_rows, "ft", "fulltext")
    profile.checkpoint("phase1_fulltext_buffered", findings=n_ft)
    _flush(search_completed=False)
    log.info(
        "[TIMING] phase1_fulltext done: fulltext=%d elapsed=%.3fs block1=%s",
        n_ft,
        time.monotonic() - t_p1,
        (layout.blocks_dir / "block_1.json").is_file(),
    )
    profile.checkpoint(
        "phase1_fulltext_done",
        findings=n_ft,
        phase_sec=round(time.monotonic() - t_p1, 4),
        block1=(layout.blocks_dir / "block_1.json").is_file(),
    )

    # ------------------------------------------------------------------ #
    # Phase 2+3: semantic and grep in parallel (optional)                #
    # ------------------------------------------------------------------ #
    grep_enabled = enable_grep and bool(grep_patterns)
    semantic_enabled = enable_semantic and semantic_limit > 0
    parallel_tasks: list[asyncio.Task[None]] = []
    if semantic_enabled:
        parallel_tasks.append(asyncio.create_task(_run_semantic_phase()))
    if grep_enabled:
        parallel_tasks.append(asyncio.create_task(_run_grep_phase()))
    if parallel_tasks:
        await asyncio.gather(*parallel_tasks)
        if not grep_enabled:
            _flush(search_completed=True)
    else:
        log.info("[TIMING] phase3_grep skipped")
        profile.checkpoint("grep_phase_skipped", reason="disabled_or_no_patterns")
        _flush(search_completed=True)

    total = time.monotonic() - t0
    block1_ready = (layout.blocks_dir / "block_1.json").is_file()
    update_manifest_atomic(
        layout,
        lambda m: replace(
            m,
            status="completed",
            phase="completion",
            last_access_at=time.time(),
            heartbeat_at=time.time(),
        ),
    )
    log.info(
        "[TIMING] run_paginated_cross done total=%.3fs block1=%s findings=%d",
        total,
        block1_ready,
        idx,
    )
    profile.checkpoint(
        "cross_run_done",
        total_sec=round(total, 4),
        block1=block1_ready,
        findings_total=idx,
    )
    return 1 if block1_ready else None
