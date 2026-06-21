"""
MCP command: fs_grep

Line-oriented search over project files on disk (``grep``), no full-text index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.progress_tracker import get_progress_tracker_from_context
from .base_mcp_command import BaseMCPCommand
from .command_metadata_helpers import finalize_command_metadata
from ..core.exceptions import ValidationError
from .fs_grep_budget import (
    GREP_BUDGET_EXCEEDED,
    GREP_HARD_TIMEOUT,
    GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
    GREP_TIMEOUT,
    FsGrepBudgetState,
    cap_candidate_paths,
    limits_for_queue,
    limits_for_sync,
    resolve_execution_mode,
    resolve_hard_timeout_seconds,
)
from ..core.index_coverage import IndexCoverageService
from ..core.search_inline_execution import (
    is_queued_search_execution,
    run_search_inline_or_queue,
)
from ..core.search_timeouts import (
    SEARCH_HARD_TIMEOUT_SECONDS,
    SEARCH_INLINE_TIMEOUT_SECONDS,
)
from ..core.structure_extraction.format_registry import (
    should_scan_path,
    validate_scan_policy,
)
from ..core.structure_extraction.match_mapper import (
    EnrichmentCounters,
    EnrichmentPolicy,
    enrich_matches_for_file,
)
from ..core.structure_extraction.stable_tree import TreeResolutionStats
from .fs_grep_sources import GrepScanTarget, build_scan_targets
from .preview_config_defaults import get_preview_config_defaults
from .file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)
from .project_fs_enumerate import enumerate_project_paths

logger = logging.getLogger(__name__)


class FsGrepCommand(BaseMCPCommand):
    """Scan files on disk for a pattern (grep-style)."""

    name = "fs_grep"
    version = "1.4.1"
    descr = (
        "Search file contents on disk (grep-style). Does not use the database full-text index; "
        "use ``fulltext_search`` for indexed search. Respects the same walk rules as "
        "``list_project_files``. Sync calls enforce wall-time and file budgets; use "
        "Slow scans auto-queue after the inline timeout (default 3s); poll "
        "queue_get_job_status for results."
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "pattern": {
                    "type": "string",
                    "description": (
                        "Search pattern. When literal=true, matched as substring per line. "
                        "When literal=false, Python ``re`` regex (multiline off; line by line)."
                    ),
                },
                "literal": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, treat pattern as plain substring (not regex).",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "default": True,
                    "description": "If false, use case-insensitive matching.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional filter on project-relative path (same rules as list_project_files "
                        "``file_pattern``)."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": "Alias of file_pattern; file_pattern wins when both set.",
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Stop after this many matching lines (default 500).",
                    "default": 500,
                    "minimum": 1,
                    "maximum": 10000,
                },
                "max_file_bytes": {
                    "type": "integer",
                    "description": (
                        "Skip individual files larger than this many bytes before opening them. "
                        "Use 0 to disable the guard. Default: 5242880 (5 MiB)."
                    ),
                    "default": 5242880,
                    "minimum": 0,
                    "maximum": 1073741824,
                },
                "line_preview_len": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100000,
                    "description": (
                        "Max characters returned per matching line. Default from server config."
                    ),
                    "nullable": True,
                },
                "scan_all": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, scan all text-readable files (CLI-grep style). If false, "
                        "only indexer/preview-supported formats."
                    ),
                },
                "include_logs": {
                    "type": "boolean",
                    "default": False,
                    "description": "When scan_all=true, include .log files unless false.",
                },
                "indexed_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, grep only files that are indexed but changed.",
                },
                "skip_indexed_unchanged": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Skip files whose content matches the current fulltext index."
                    ),
                },
                "source": {
                    "type": "string",
                    "enum": ["disk", "draft_session", "both"],
                    "default": "disk",
                    "description": "Search disk files, universal_file draft, or both.",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "universal_file session id; required when source includes draft_session."
                    ),
                },
                "fast_text_only": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, return line matches without structure extraction."
                    ),
                },
                "enrich_blocks": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true, enrich matches with preview-compatible block metadata "
                        "(first enrich_max_results per file)."
                    ),
                },
                "enrich_max_results": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 0,
                    "maximum": 200,
                    "description": "Max matches to enrich when enrich_blocks=true.",
                },
                "ensure_persisted_tree": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When enriching, use persisted CST sidecar/tree ids only "
                        "(rebuild missing/stale trees before returning node_ref)."
                    ),
                },
                "stable_ids_required": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "If true, omit node_ref/block_id when stable ids cannot be guaranteed."
                    ),
                },
                "grep_sync_max_wall_seconds": {
                    "type": "number",
                    "minimum": 5,
                    "maximum": 600,
                    "description": (
                        "Sync-only total wall-time budget. Ignored when executed via job queue."
                    ),
                },
                "hard_timeout_seconds": {
                    "type": "number",
                    "default": SEARCH_HARD_TIMEOUT_SECONDS,
                    "minimum": 1,
                    "maximum": 3600,
                    "description": (
                        "Hard execution timeout. If exceeded, grep is stopped at the transport "
                        "boundary and returns GREP_HARD_TIMEOUT (success=false)."
                    ),
                },
                "auto_queue_on_inline_timeout": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true (default), sync calls that exceed inline_timeout_seconds "
                        "are enqueued automatically and return job_id."
                    ),
                },
                "inline_timeout_seconds": {
                    "type": "number",
                    "default": SEARCH_INLINE_TIMEOUT_SECONDS,
                    "minimum": 0.1,
                    "maximum": 30,
                    "description": (
                        "Wall-time cap for the initial inline attempt before auto-queue."
                    ),
                },
                "show_venv": {"type": "boolean", "default": False},
                "python_only": {"type": "boolean", "default": False},
                "include_venv_ignore_exceptions": {"type": "boolean", "default": False},
                "show_hidden": {"type": "boolean", "default": False},
            },
            "required": ["project_id", "pattern"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject bounded parameters outside schema min/max after schema validation."""
        params = super().validate_params(params)
        schema = self.get_schema()
        props = schema.get("properties") or {}
        for key in (
            "max_matches",
            "enrich_max_results",
            "max_file_bytes",
            "line_preview_len",
            "grep_sync_max_wall_seconds",
            "hard_timeout_seconds",
            "inline_timeout_seconds",
        ):
            if key not in params or params[key] is None:
                continue
            value = params[key]
            prop = props.get(key) or {}
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be >= {minimum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
            if maximum is not None and value > maximum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be <= {maximum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
        source = str(params.get("source") or "disk")
        if source not in ("disk", "draft_session", "both"):
            raise ValidationError(
                "source must be disk, draft_session, or both",
                field="source",
            )
        if (
            source in ("draft_session", "both")
            and not str(params.get("session_id") or "").strip()
        ):
            raise ValidationError(
                "session_id is required when source includes draft_session",
                field="session_id",
            )
        policy_err = validate_scan_policy(
            scan_all=bool(params.get("scan_all")),
            include_logs=bool(params.get("include_logs")),
        )
        if policy_err:
            raise ValidationError(
                "include_logs=true requires scan_all=true",
                field="include_logs",
                details={"code": policy_err},
            )
        return params

    async def execute(
        self,
        project_id: str,
        pattern: str,
        literal: bool = True,
        case_sensitive: bool = True,
        file_pattern: Optional[str] = None,
        glob: Optional[str] = None,
        max_matches: int = 500,
        max_file_bytes: int = 5 * 1024 * 1024,
        line_preview_len: Optional[int] = None,
        scan_all: bool = False,
        include_logs: bool = False,
        indexed_only: bool = False,
        skip_indexed_unchanged: bool = True,
        source: str = "disk",
        session_id: Optional[str] = None,
        fast_text_only: bool = False,
        enrich_blocks: bool = True,
        enrich_max_results: int = 50,
        ensure_persisted_tree: bool = True,
        stable_ids_required: bool = True,
        grep_sync_max_wall_seconds: Optional[float] = None,
        hard_timeout_seconds: Optional[float] = None,
        show_venv: bool = False,
        python_only: bool = False,
        include_venv_ignore_exceptions: bool = False,
        show_hidden: bool = False,
        max_files_scanned: Optional[int] = None,
        wall_time_budget_s: Optional[float] = None,
        auto_queue_on_inline_timeout: bool = True,
        inline_timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Run grep off the event loop; inline attempt may auto-queue on timeout."""
        context = kwargs.get("context") or {}
        if not isinstance(context, dict):
            context = {}
        on_match_batch = kwargs.get("on_match_batch")
        enqueue_params = {
            k: v
            for k, v in {
                "project_id": project_id,
                "pattern": pattern,
                "literal": literal,
                "case_sensitive": case_sensitive,
                "file_pattern": file_pattern,
                "glob": glob,
                "max_matches": max_matches,
                "max_file_bytes": max_file_bytes,
                "line_preview_len": line_preview_len,
                "scan_all": scan_all,
                "include_logs": include_logs,
                "indexed_only": indexed_only,
                "skip_indexed_unchanged": skip_indexed_unchanged,
                "source": source,
                "session_id": session_id,
                "fast_text_only": fast_text_only,
                "enrich_blocks": enrich_blocks,
                "enrich_max_results": enrich_max_results,
                "ensure_persisted_tree": ensure_persisted_tree,
                "stable_ids_required": stable_ids_required,
                "grep_sync_max_wall_seconds": grep_sync_max_wall_seconds,
                "hard_timeout_seconds": hard_timeout_seconds,
                "show_venv": show_venv,
                "python_only": python_only,
                "include_venv_ignore_exceptions": include_venv_ignore_exceptions,
                "show_hidden": show_hidden,
                "max_files_scanned": max_files_scanned,
                "wall_time_budget_s": wall_time_budget_s,
                "auto_queue_on_inline_timeout": auto_queue_on_inline_timeout,
                "inline_timeout_seconds": inline_timeout_seconds,
            }.items()
            if v is not None
        }

        cancel_event = threading.Event()

        async def _run() -> SuccessResult | ErrorResult:
            return await self._execute_grep(
                project_id=project_id,
                pattern=pattern,
                literal=literal,
                case_sensitive=case_sensitive,
                file_pattern=file_pattern,
                glob=glob,
                max_matches=max_matches,
                max_file_bytes=max_file_bytes,
                line_preview_len=line_preview_len,
                scan_all=scan_all,
                include_logs=include_logs,
                indexed_only=indexed_only,
                skip_indexed_unchanged=skip_indexed_unchanged,
                source=source,
                session_id=session_id,
                fast_text_only=fast_text_only,
                enrich_blocks=enrich_blocks,
                enrich_max_results=enrich_max_results,
                ensure_persisted_tree=ensure_persisted_tree,
                stable_ids_required=stable_ids_required,
                grep_sync_max_wall_seconds=grep_sync_max_wall_seconds,
                hard_timeout_seconds=hard_timeout_seconds,
                show_venv=show_venv,
                python_only=python_only,
                include_venv_ignore_exceptions=include_venv_ignore_exceptions,
                show_hidden=show_hidden,
                max_files_scanned=max_files_scanned,
                wall_time_budget_s=wall_time_budget_s,
                context=context,
                cancel_event=cancel_event,
                on_match_batch=on_match_batch,
            )

        return await run_search_inline_or_queue(
            command_name=self.name,
            params=enqueue_params,
            context=context,
            auto_queue_on_inline_timeout=auto_queue_on_inline_timeout,
            inline_timeout_seconds=inline_timeout_seconds,
            execute_fn=_run,
            cancel_event=cancel_event,
        )

    async def _execute_grep(
        self,
        *,
        project_id: str,
        pattern: str,
        literal: bool,
        case_sensitive: bool,
        file_pattern: Optional[str],
        glob: Optional[str],
        max_matches: int,
        max_file_bytes: int,
        line_preview_len: Optional[int],
        scan_all: bool,
        include_logs: bool,
        indexed_only: bool,
        skip_indexed_unchanged: bool,
        source: str,
        session_id: Optional[str],
        fast_text_only: bool,
        enrich_blocks: bool,
        enrich_max_results: int,
        ensure_persisted_tree: bool,
        stable_ids_required: bool,
        grep_sync_max_wall_seconds: Optional[float],
        hard_timeout_seconds: Optional[float],
        show_venv: bool,
        python_only: bool,
        include_venv_ignore_exceptions: bool,
        show_hidden: bool,
        max_files_scanned: Optional[int],
        wall_time_budget_s: Optional[float],
        context: Dict[str, Any],
        cancel_event: Optional[threading.Event] = None,
        on_match_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    ) -> SuccessResult | ErrorResult:
        """Worker: grep with hard timeout; cooperative cancel when inline times out."""
        in_queue = is_queued_search_execution(context=context)
        if in_queue:
            limits = limits_for_queue(max_matches=max_matches)
        else:
            limits = limits_for_sync(
                max_matches=max_matches,
                grep_sync_max_wall_seconds=grep_sync_max_wall_seconds,
            )
        if max_files_scanned is not None:
            limits.max_files_scanned = max(1, int(max_files_scanned))
        wall_budget = (
            float(wall_time_budget_s)
            if wall_time_budget_s is not None
            else limits.max_wall_seconds
        )
        hard_limit = resolve_hard_timeout_seconds(
            explicit=hard_timeout_seconds,
            in_queue=in_queue,
        )
        stage_holder: Dict[str, str] = {"stage": "candidate_enumeration"}
        started = perf_counter()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._execute_sync,
                    project_id,
                    pattern,
                    literal,
                    case_sensitive,
                    file_pattern,
                    glob,
                    max_matches,
                    max_file_bytes,
                    line_preview_len,
                    scan_all,
                    include_logs,
                    indexed_only,
                    skip_indexed_unchanged,
                    source,
                    session_id,
                    fast_text_only,
                    enrich_blocks,
                    enrich_max_results,
                    ensure_persisted_tree,
                    stable_ids_required,
                    show_venv,
                    python_only,
                    include_venv_ignore_exceptions,
                    show_hidden,
                    limits,
                    in_queue,
                    wall_budget,
                    stage_holder,
                    cancel_event,
                    on_match_batch,
                ),
                timeout=hard_limit,
            )
        except asyncio.TimeoutError:
            elapsed = perf_counter() - started
            return ErrorResult(
                message="fs_grep exceeded hard timeout and was stopped.",
                code=GREP_HARD_TIMEOUT,
                details={
                    "hard_timeout_seconds": hard_limit,
                    "elapsed_seconds": round(elapsed, 3),
                    "files_scanned": None,
                    "matches_returned": None,
                    "stage": stage_holder.get("stage") or "unknown",
                },
            )

    def _execute_sync(
        self,
        project_id: str,
        pattern: str,
        literal: bool,
        case_sensitive: bool,
        file_pattern: Optional[str],
        glob: Optional[str],
        max_matches: int,
        max_file_bytes: int,
        line_preview_len: Optional[int],
        scan_all: bool,
        include_logs: bool,
        indexed_only: bool,
        skip_indexed_unchanged: bool,
        source: str,
        session_id: Optional[str],
        fast_text_only: bool,
        enrich_blocks: bool,
        enrich_max_results: int,
        ensure_persisted_tree: bool,
        stable_ids_required: bool,
        show_venv: bool,
        python_only: bool,
        include_venv_ignore_exceptions: bool,
        show_hidden: bool,
        limits: Any,
        in_queue: bool,
        wall_budget: float,
        stage_holder: Optional[Dict[str, str]] = None,
        cancel_event: Optional[threading.Event] = None,
        on_match_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    ) -> SuccessResult | ErrorResult:
        """Phase-1 fast text scan; optional phase-2 stable block enrichment."""

        def _set_stage(name: str) -> None:
            if stage_holder is not None:
                stage_holder["stage"] = name

        if not (pattern or "").strip():
            return ErrorResult(
                message="pattern must be non-empty",
                code="INVALID_PATTERN",
                details={},
            )
        if max_matches < 1:
            return ErrorResult(
                message="max_matches must be >= 1",
                code="INVALID_LIMIT",
                details={"max_matches": max_matches},
            )
        if max_file_bytes < 0:
            return ErrorResult(
                message="max_file_bytes must be >= 0",
                code="INVALID_LIMIT",
                details={"max_file_bytes": max_file_bytes},
            )
        cfg = get_preview_config_defaults()
        if line_preview_len is None:
            line_preview_len = int(cfg["grep_line_preview_len_default"])
        if line_preview_len < 1:
            return ErrorResult(
                message="line_preview_len must be >= 1",
                code="INVALID_LIMIT",
                details={"line_preview_len": line_preview_len},
            )

        budget = FsGrepBudgetState(limits=limits)
        budget.limits.max_wall_seconds = wall_budget
        if cancel_event is not None:
            budget.should_cancel = cancel_event.is_set
        effective_max_matches = min(max_matches, limits.max_matches)

        try:
            started_at = perf_counter()
            _set_stage("candidate_enumeration")
            project_root = self._resolve_project_root(project_id).resolve()
            fs_paths = enumerate_project_paths(
                project_root,
                show_venv=show_venv,
                python_only=python_only,
                include_venv_ignore_exceptions=include_venv_ignore_exceptions,
                show_hidden=show_hidden,
            )
            effective_pattern = effective_listing_pattern(file_pattern, glob)
            if effective_pattern:
                fs_paths = [
                    p
                    for p in fs_paths
                    if relative_path_matches_listing_pattern(
                        canonical_relative_path(project_root, p), effective_pattern
                    )
                ]
            fs_paths = [
                p
                for p in fs_paths
                if should_scan_path(
                    canonical_relative_path(project_root, p),
                    scan_all=scan_all,
                    include_logs=include_logs,
                )
            ]
            coverage_by_rel: Dict[str, Any] = {}
            if skip_indexed_unchanged or indexed_only:
                database = None
                try:
                    database = self._open_database_from_config(auto_analyze=False)
                    coverage = IndexCoverageService(database, project_id, project_root)
                    rels = [canonical_relative_path(project_root, p) for p in fs_paths]
                    kept, coverage_by_rel = (
                        coverage.filter_grep_candidates_with_reasons(
                            rels,
                            skip_indexed_unchanged=skip_indexed_unchanged,
                            indexed_only=indexed_only,
                        )
                    )
                    kept_set = set(kept)
                    fs_paths = [
                        p
                        for p in fs_paths
                        if canonical_relative_path(project_root, p) in kept_set
                    ]
                except Exception as cov_err:
                    budget.add_warning(
                        "INDEX_COVERAGE_SKIPPED",
                        f"Index coverage filter skipped: {cov_err}",
                    )
                finally:
                    if database is not None:
                        try:
                            database.disconnect()
                        except Exception:
                            pass
            fs_paths = cap_candidate_paths(fs_paths, budget)
            scan_targets, source_warnings = build_scan_targets(
                project_root=project_root,
                fs_paths=fs_paths,
                source=source,  # type: ignore[arg-type]
                session_id=session_id,
            )
            for sw in source_warnings:
                budget.add_warning(
                    sw.get("code", "SOURCE_WARNING"), sw.get("message", "")
                )

            logger.info(
                "fs_grep start project_id=%s root=%s pattern=%r literal=%s "
                "case_sensitive=%s file_pattern=%r max_matches=%s max_file_bytes=%s "
                "candidate_files=%s fast_text_only=%s enrich_blocks=%s mode=%s",
                project_id,
                project_root,
                pattern,
                literal,
                case_sensitive,
                effective_pattern,
                effective_max_matches,
                max_file_bytes,
                budget.usage.candidate_files,
                fast_text_only,
                enrich_blocks,
                limits.mode,
            )

            flags = 0 if case_sensitive else re.IGNORECASE
            needle = pattern
            regex: Optional[re.Pattern[str]] = None
            if not literal:
                try:
                    regex = re.compile(needle, flags)
                except re.error as e:
                    return ErrorResult(
                        message=f"Invalid regex: {e}",
                        code="INVALID_REGEX",
                        details={"pattern": needle},
                    )

            _set_stage("line_scan")
            tree_stats = TreeResolutionStats()
            enrich_counters = EnrichmentCounters()
            enrichment_policy = {
                "ensure_persisted_tree": ensure_persisted_tree,
                "stable_ids_required": stable_ids_required,
            }
            enrich_policy = EnrichmentPolicy(
                ensure_persisted_tree=ensure_persisted_tree,
                stable_ids_required=stable_ids_required,
            )
            enrich_applied = 0

            def _deliver_file_matches(file_batch: List[Dict[str, Any]]) -> None:
                nonlocal enrich_applied
                if on_match_batch is None or not file_batch:
                    return
                batch = list(file_batch)
                if fast_text_only:
                    for row in batch:
                        _set_line_only_match(row, "skipped_fast_text_only")
                    enrich_counters.enrichment_skipped += len(batch)
                elif enrich_blocks:
                    remaining = max(0, enrich_max_results - enrich_applied)
                    if remaining <= 0:
                        for row in batch:
                            _set_line_only_match(row, "skipped_budget")
                        enrich_counters.enrichment_skipped += len(batch)
                    else:
                        _set_stage("structure_extraction")
                        _phase2_enrich_blocks(
                            project_root=project_root,
                            matches=batch,
                            enrich_max_results=remaining,
                            budget=budget,
                            policy=enrich_policy,
                            tree_stats=tree_stats,
                            counters=enrich_counters,
                        )
                        enrich_applied += min(remaining, len(batch))
                on_match_batch(batch)

            matches, scan_stats = _phase1_text_scan_targets(
                project_root=project_root,
                scan_targets=scan_targets,
                needle=needle,
                literal=literal,
                case_sensitive=case_sensitive,
                regex=regex,
                max_matches=effective_max_matches,
                max_file_bytes=max_file_bytes,
                line_preview_len=line_preview_len,
                budget=budget,
                scan_all=scan_all,
                coverage_by_rel=coverage_by_rel,
                on_file_matches=(
                    _deliver_file_matches if on_match_batch is not None else None
                ),
            )

            if on_match_batch is None:
                if fast_text_only and matches:
                    for row in matches:
                        _set_line_only_match(row, "skipped_fast_text_only")
                    budget.add_warning(
                        GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
                        "Structural enrichment skipped because fast_text_only=true.",
                        enrich_max_results=enrich_max_results,
                    )
                    enrich_counters.enrichment_skipped += len(matches)
                elif enrich_blocks and matches:
                    _set_stage("structure_extraction")
                    _phase2_enrich_blocks(
                        project_root=project_root,
                        matches=matches,
                        enrich_max_results=enrich_max_results,
                        budget=budget,
                        policy=enrich_policy,
                        tree_stats=tree_stats,
                        counters=enrich_counters,
                    )

            budget.usage.matches_returned = len(matches)
            budget.usage.files_scanned = scan_stats["files_scanned"]
            budget.finalize()

            if budget.usage.budget_exceeded:
                budget.warnings.append(budget.budget_warning())

            execution_mode = resolve_execution_mode(
                in_queue=in_queue,
                budget=budget,
                candidate_files=budget.usage.candidate_files,
            )

            elapsed = perf_counter() - started_at
            logger.info(
                "fs_grep done project_id=%s elapsed=%.3fs matches=%s "
                "files_scanned=%s files_skipped_large=%s files_skipped_io=%s "
                "truncated=%s budget_exceeded=%s execution_mode=%s",
                project_id,
                elapsed,
                len(matches),
                scan_stats["files_scanned"],
                scan_stats["files_skipped_large"],
                scan_stats["files_skipped_io"],
                len(matches) >= effective_max_matches,
                budget.usage.budget_exceeded,
                execution_mode,
            )

            payload: Dict[str, Any] = {
                "success": True,
                "pattern": needle,
                "literal": literal,
                "case_sensitive": case_sensitive,
                "matches": matches,
                "match_count": len(matches),
                "files_scanned": scan_stats["files_scanned"],
                "files_skipped_large": scan_stats["files_skipped_large"],
                "files_skipped_io": scan_stats["files_skipped_io"],
                "skipped_large_samples": scan_stats["skipped_large_samples"],
                "truncated": len(matches) >= effective_max_matches,
                "budget_exceeded": budget.usage.budget_exceeded,
                "budget_reason": budget.usage.exceed_reason,
                "execution_mode": execution_mode,
                "grep_budget": {
                    "limits": budget.limits.as_dict(),
                    "usage": budget.usage.as_dict(),
                },
                "warnings": list(budget.warnings),
                "fast_text_only": fast_text_only,
                "enrich_blocks": enrich_blocks,
                "scan_all": scan_all,
                "source": source,
                "session_id": session_id,
                "skip_indexed_unchanged": skip_indexed_unchanged,
                "include_logs": include_logs,
                "known_types_only": not scan_all,
                "enrichment_policy": enrichment_policy,
                "structure_stats": {
                    **tree_stats.as_dict(),
                    **enrich_counters.as_dict(),
                },
            }
            if execution_mode == "queued_recommended":
                payload["use_queue_recommended"] = True

            _trim_response_payload(payload, budget)

            return SuccessResult(data=payload)
        except Exception as e:
            return self._handle_error(e, "FS_GREP_ERROR", "fs_grep")

    @classmethod
    def metadata(cls: type["FsGrepCommand"]) -> Dict[str, Any]:
        return finalize_command_metadata(
            cls,
            {
                "detailed_description": (
                    "Two-phase grep: phase-1 streams UTF-8 lines with ``fast_text_only=false`` "
                    "(default). Optional phase-2 ``enrich_blocks`` (default true) resolves block_id "
                    "for the first ``enrich_max_results`` hits only. Sync calls enforce "
                    "wall-time, scanned-file, and match budgets; heavy scans should use "
                    "``use_queue=true`` (command class sets use_queue)."
                ),
                "return_value": {
                    "success": {
                        "description": "Matches, scan stats, grep_budget, warnings.",
                        "data": {},
                        "example": {},
                    },
                    "error": {
                        "description": "Validation, budget timeout, or IO failure.",
                        "code": "FS_GREP_ERROR",
                        "message": "Human-readable message",
                    },
                },
                "usage_examples": [
                    {
                        "description": "Fast sync grep (default)",
                        "command": {
                            "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                            "pattern": "xpath",
                            "file_pattern": "code_analysis",
                            "max_matches": 50,
                        },
                        "explanation": "Returns within sync budgets; block_id null unless enrich_blocks.",
                    },
                ],
                "error_cases": {
                    "INVALID_PATTERN": {
                        "description": "The pattern is empty or whitespace only.",
                        "message": "pattern must be non-empty",
                        "solution": "Pass a non-empty search string.",
                    },
                    "GREP_HARD_TIMEOUT": {
                        "description": (
                            "Hard execution timeout exceeded; grep was stopped at the transport boundary."
                        ),
                        "message": "fs_grep exceeded hard timeout and was stopped.",
                        "solution": (
                            "Narrow file_pattern, reduce scope, or increase hard_timeout_seconds "
                            "within the allowed maximum."
                        ),
                    },
                    "GREP_TIMEOUT": {
                        "description": "Sync wall-time budget exceeded at transport layer.",
                        "message": "fs_grep exceeded sync wall-time budget",
                        "solution": "Use use_queue=true on call_server.",
                    },
                    "GREP_BUDGET_EXCEEDED": {
                        "description": "Scan stopped due to file/match/time budget (success with warnings).",
                        "message": "Grep scan stopped early",
                        "solution": "Narrow file_pattern or use use_queue=true.",
                    },
                    "GREP_TOO_MANY_FILES": {
                        "description": "Too many candidate paths for sync; list was capped.",
                        "message": "Candidate file list truncated",
                        "solution": "Use file_pattern or use_queue=true.",
                    },
                },
                "best_practices": [
                    "Keep fast_text_only=true for broad sync grep when you do not need block_id.",
                    "Use enrich_blocks only when you need block_id on a small result set.",
                    "Heavy scans: call_server(..., use_queue=true) and poll queue_get_job_status.",
                    "Narrow with file_pattern whenever possible.",
                ],
            },
        )


def _grep_match_source_label(
    *,
    target: GrepScanTarget,
    scan_all: bool,
    coverage_by_rel: Dict[str, Any],
) -> str:
    if target.source == "draft_session":
        return "grep_draft"
    rel = target.relative_path
    cov = coverage_by_rel.get(rel)
    if cov is not None:
        reason = getattr(cov, "reason", None) or (
            cov.get("reason") if isinstance(cov, dict) else None
        )
        if reason == "changed_since_index":
            return "grep_changed"
        if reason == "indexed_current":
            return "grep_line_only"
    if scan_all:
        return "grep_scan_all"
    return "grep_unindexed"


def _set_line_only_match(row: Dict[str, Any], status: str) -> None:
    for key in (
        "block_id",
        "block_type",
        "node_ref",
        "selector",
        "preview",
        "name",
        "qualname",
        "start_line",
        "end_line",
    ):
        row.pop(key, None)
    row["enrichment_status"] = status


def _phase1_text_scan_targets(
    *,
    project_root: Any,
    scan_targets: List[GrepScanTarget],
    needle: str,
    literal: bool,
    case_sensitive: bool,
    regex: Optional[re.Pattern[str]],
    max_matches: int,
    max_file_bytes: int,
    line_preview_len: int,
    budget: FsGrepBudgetState,
    scan_all: bool = False,
    coverage_by_rel: Optional[Dict[str, Any]] = None,
    on_file_matches: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    files_scanned = 0
    files_skipped_large = 0
    files_skipped_io = 0
    skipped_large_samples: List[Dict[str, Any]] = []

    for target in scan_targets:
        if len(matches) >= max_matches:
            break
        if budget.should_stop_scan(
            matches_count=len(matches), files_scanned=files_scanned
        ):
            break

        rel = target.relative_path
        if target.source == "disk":
            abs_path = (project_root / rel).resolve()
            try:
                size = abs_path.stat().st_size
            except OSError:
                files_skipped_io += 1
                continue
            if max_file_bytes and size > max_file_bytes:
                files_skipped_large += 1
                if len(skipped_large_samples) < 20:
                    skipped_large_samples.append(
                        {"relative_path": rel, "size_bytes": size}
                    )
                continue

        files_scanned += 1
        file_matches: List[Dict[str, Any]] = []
        try:
            text = target.read_content(project_root)
        except ValueError as exc:
            code = str(exc).split(":")[0] if ":" in str(exc) else str(exc)
            budget.add_warning(code, str(exc), relative_path=rel)
            files_skipped_io += 1
            continue
        except OSError:
            files_skipped_io += 1
            continue

        for i, raw_line in enumerate(text.splitlines(), start=1):
            if len(matches) >= max_matches:
                break
            if budget.should_stop_scan(
                matches_count=len(matches),
                files_scanned=files_scanned,
            ):
                break
            if "\0" in raw_line:
                break
            raw_line = raw_line.rstrip("\r\n")
            ok = _line_matches(
                raw_line,
                needle=needle,
                literal=literal,
                case_sensitive=case_sensitive,
                regex=regex,
            )
            if ok:
                line_text = raw_line
                if len(line_text) > line_preview_len:
                    line_text = line_text[:line_preview_len]
                row: Dict[str, Any] = {
                    "relative_path": rel,
                    "line_number": i,
                    "line": line_text,
                    "source": _grep_match_source_label(
                        target=target,
                        scan_all=scan_all,
                        coverage_by_rel=coverage_by_rel or {},
                    ),
                    "grep_source": target.source,
                }
                if target.session_id:
                    row["session_id"] = target.session_id
                matches.append(row)
                file_matches.append(row)

        if file_matches and on_file_matches is not None:
            on_file_matches(file_matches)

    return matches, {
        "files_scanned": files_scanned,
        "files_skipped_large": files_skipped_large,
        "files_skipped_io": files_skipped_io,
        "skipped_large_samples": skipped_large_samples,
    }


def _line_matches(
    raw_line: str,
    *,
    needle: str,
    literal: bool,
    case_sensitive: bool,
    regex: Optional[re.Pattern[str]],
) -> bool:
    if literal:
        hay = raw_line if case_sensitive else raw_line.lower()
        nd = needle if case_sensitive else needle.lower()
        return nd in hay
    assert regex is not None
    return regex.search(raw_line) is not None


def _phase2_enrich_blocks(
    *,
    project_root: Any,
    matches: List[Dict[str, Any]],
    enrich_max_results: int,
    budget: FsGrepBudgetState,
    policy: EnrichmentPolicy,
    tree_stats: TreeResolutionStats,
    counters: EnrichmentCounters,
) -> None:
    if enrich_max_results <= 0:
        budget.add_warning(
            GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
            "enrich_max_results=0; no structural enrichment performed.",
        )
        for row in matches:
            _set_line_only_match(row, "skipped_budget")
        counters.enrichment_skipped += len(matches)
        return

    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for row in matches:
        rel = str(row.get("relative_path") or "")
        by_file.setdefault(rel, []).append(row)

    enriched = 0
    for rel, rows in by_file.items():
        if enriched >= enrich_max_results:
            for row in rows:
                _set_line_only_match(row, "skipped_budget")
            counters.enrichment_skipped += len(rows)
            continue
        if budget.should_stop_scan(
            matches_count=len(matches),
            files_scanned=budget.usage.files_scanned,
        ):
            break
        session_id = rows[0].get("session_id")
        src = "draft_session" if session_id else "disk"
        try:
            if session_id:
                from code_analysis.commands.fs_grep_sources import (
                    read_draft_session_content,
                )

                content = read_draft_session_content(str(session_id))
            else:
                content = (project_root / rel).read_text(
                    encoding="utf-8", errors="replace"
                )
        except Exception as exc:
            budget.add_warning(
                "STRUCTURE_TREE_ENRICHMENT_FAILED",
                str(exc),
                relative_path=rel,
            )
            counters.enrichment_failed += len(rows)
            for row in rows:
                _set_line_only_match(row, "skipped_extractor_error")
            continue
        remaining = enrich_max_results - enriched
        abs_file = str((project_root / rel).resolve())
        doc_warnings = enrich_matches_for_file(
            rows,
            file_path=abs_file,
            content=content,
            source=src,
            session_id=str(session_id) if session_id else None,
            max_rows=remaining,
            policy=policy,
            tree_stats=tree_stats,
            counters=counters,
            preview_file_path=rel,
        )
        for w in doc_warnings:
            budget.add_warning(w.get("code", "STRUCTURE_WARNING"), w.get("message", ""))
        enriched += sum(
            1 for row in rows[:remaining] if row.get("enrichment_status") == "enriched"
        )

    if enriched < len(matches):
        budget.add_warning(
            GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
            (
                f"Structural enrichment applied to {enriched} of {len(matches)} "
                "matches (per-file budget)."
            ),
            enrich_max_results=enrich_max_results,
            matches_total=len(matches),
        )


def _trim_response_payload(payload: Dict[str, Any], budget: FsGrepBudgetState) -> None:
    try:
        size = len(json.dumps(payload, default=str).encode("utf-8"))
    except Exception:
        return
    if size <= budget.limits.max_response_bytes:
        return
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return
    while matches:
        matches.pop()
        size = len(json.dumps(payload, default=str).encode("utf-8"))
        if size <= budget.limits.max_response_bytes:
            payload["match_count"] = len(matches)
            budget.mark_exceeded("max_response_bytes")
            budget.warnings.append(
                {
                    "code": GREP_BUDGET_EXCEEDED,
                    "message": "Matches truncated to fit response size budget.",
                    "suggestion": "call_server(..., use_queue=true)",
                }
            )
            return
