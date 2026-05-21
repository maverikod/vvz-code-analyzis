"""
MCP command: project_cross_search.

Orchestrates semantic_search, fulltext_search, and fs_grep into one ranked
evidence map grouped by project-relative file path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.progress_tracker import get_progress_tracker_from_context
from ..core.search_inline_execution import (
    is_queued_search_execution,
    run_search_inline_or_queue,
)
from ..core.search_timeouts import (
    SEARCH_INLINE_TIMEOUT_SECONDS,
    resolve_inline_timeout_seconds,
)
from .base_mcp_command import BaseMCPCommand
from .fs_grep_budget import (
    GREP_HARD_TIMEOUT,
    clamp_hard_timeout_seconds,
    resolve_hard_timeout_seconds,
)
from .fs_grep_command import FsGrepCommand
from .project_cross_search_grep_budget import (
    GREP_BUDGET_EXCEEDED,
    GrepBudgetState,
    ExecutionMode,
    limits_for_queued_job,
    limits_for_sync,
    resolve_execution_mode,
    trim_payload_to_budget,
)
from .project_cross_search_core import (
    GREP_LINE_ONLY_IGNORED,
    MODES,
    PROFILES,
    PathFilterOptions,
    SearchPlan,
    build_command_audit,
    build_grep_pattern_list,
    build_summary,
    merge_evidence,
    normalize_fulltext_hit,
    normalize_grep_hit,
    normalize_semantic_hit,
    partition_grep_for_cross_search,
)
from .search import SearchCommand
from .semantic_search_mcp import SemanticSearchMCPCommand

logger = logging.getLogger(__name__)


def _bounded_int_param(
    params: Dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    """Preserve explicit zero; only substitute default when key is omitted or None."""
    if key not in params or params[key] is None:
        return default
    return max(minimum, min(maximum, int(params[key])))


def get_project_cross_search_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["project_id", "query"],
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project UUID. Use list_projects to discover valid project_id values.",
            },
            "query": {
                "type": "string",
                "description": (
                    "Natural-language or keyword query shared by semantic and full-text search."
                ),
            },
            "grep_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": (
                    "Exact or regex patterns for fs_grep. If empty, simple markers may be "
                    "derived from query; explicit grep_patterns are preferred for audits."
                ),
            },
            "file_pattern": {
                "type": "string",
                "default": "",
                "description": (
                    "Optional project-relative path filter passed to fs_grep and used "
                    "for filtering merged results."
                ),
            },
            "entity_type": {
                "type": "string",
                "enum": [
                    "file",
                    "class",
                    "function",
                    "method",
                    "variable",
                    "attribute",
                ],
                "description": "Optional fulltext entity type filter.",
            },
            "mode": {
                "type": "string",
                "default": "intersection",
                "enum": list(MODES),
                "description": "Result filtering mode.",
            },
            "profile": {
                "type": "string",
                "default": "generic",
                "enum": list(PROFILES),
                "description": "Optional preset that expands grep patterns and scoring rules.",
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "minimum": 1,
                "maximum": 200,
                "description": "Maximum merged results returned.",
            },
            "semantic_limit": {
                "type": "integer",
                "default": 30,
                "minimum": 0,
                "maximum": 200,
            },
            "fulltext_limit": {
                "type": "integer",
                "default": 30,
                "minimum": 0,
                "maximum": 200,
            },
            "grep_limit": {
                "type": "integer",
                "default": 200,
                "minimum": 0,
                "maximum": 2000,
            },
            "min_semantic_score": {
                "type": "number",
                "default": 0.45,
                "minimum": 0,
                "maximum": 1,
            },
            "case_sensitive": {
                "type": "boolean",
                "default": False,
            },
            "literal": {
                "type": "boolean",
                "default": True,
                "description": "Passed to fs_grep for explicit grep_patterns.",
            },
            "include_docs": {
                "type": "boolean",
                "default": True,
            },
            "include_tests": {
                "type": "boolean",
                "default": True,
            },
            "include_hidden": {
                "type": "boolean",
                "default": False,
            },
            "include_venv": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Must default to false and must not scan .venv unless explicitly requested."
                ),
            },
            "grep_sync_max_wall_seconds": {
                "type": "number",
                "minimum": 5,
                "maximum": 600,
                "description": (
                    "Sync-only cap on total grep wall time across all patterns. "
                    "Ignored when the command runs via the job queue (use_queue=true)."
                ),
            },
            "grep_hard_timeout_seconds": {
                "type": "number",
                "minimum": 1,
                "maximum": 3600,
                "description": (
                    "Hard timeout for all fs_grep calls in this cross-search. When omitted, "
                    "defaults to 30s for sync and 120s for queued execution."
                ),
            },
            "fast_text_only": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Forwarded to fs_grep. Not allowed when require_structural_grep=true."
                ),
            },
            "grep_scope": {
                "type": "string",
                "enum": ["index_gap", "all", "changed", "draft_only"],
                "default": "index_gap",
                "description": (
                    "index_gap: grep only unindexed/changed files (skip indexed unchanged). "
                    "all: no index filter. changed: indexed but stale. draft_only: session only."
                ),
            },
            "scan_all": {
                "type": "boolean",
                "default": False,
                "description": "Forwarded to fs_grep: scan all text files vs known formats only.",
            },
            "source": {
                "type": "string",
                "enum": ["disk", "draft_session", "both"],
                "default": "disk",
                "description": "Forwarded to fs_grep for disk vs draft session search.",
            },
            "session_id": {
                "type": "string",
                "description": "universal_file session id when source includes draft_session.",
            },
            "require_structural_grep": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true (default), only grep matches with enrichment_status=enriched "
                    "and preview-compatible node_ref/selector count as cross-search evidence."
                ),
            },
            "debug": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Include diagnostics.grep_line_only for grep hits ignored as non-structural."
                ),
            },
            "auto_queue_on_inline_timeout": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true (default), sync calls exceeding inline_timeout_seconds "
                    "enqueue the full project_cross_search command and return job_id."
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
        },
    }


class ProjectCrossSearchCommand(BaseMCPCommand):
    """Run semantic, full-text, and grep search; merge evidence by file path."""

    name = "project_cross_search"
    version = "1.1.0"
    descr = (
        "Cross-search orchestrator combining semantic_search, fulltext_search, and fs_grep "
        "into ranked evidence grouped by file path with confidence labels."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return get_project_cross_search_schema()

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        query = str(params.get("query") or "").strip()
        if not query:
            from ..core.exceptions import ValidationError

            raise ValidationError("query must be non-empty", field="query")
        params["query"] = query

        mode = str(params.get("mode") or "intersection")
        if mode not in MODES:
            from ..core.exceptions import ValidationError

            raise ValidationError(
                f"mode must be one of {list(MODES)}",
                field="mode",
            )
        profile = str(params.get("profile") or "generic")
        if profile not in PROFILES:
            from ..core.exceptions import ValidationError

            raise ValidationError(
                f"profile must be one of {list(PROFILES)}",
                field="profile",
            )

        params["limit"] = _bounded_int_param(
            params, "limit", 20, minimum=1, maximum=200
        )
        params["semantic_limit"] = _bounded_int_param(
            params, "semantic_limit", 30, minimum=0, maximum=200
        )
        params["fulltext_limit"] = _bounded_int_param(
            params, "fulltext_limit", 30, minimum=0, maximum=200
        )
        params["grep_limit"] = _bounded_int_param(
            params, "grep_limit", 200, minimum=0, maximum=2000
        )
        params["min_semantic_score"] = max(
            0.0, min(1.0, float(params.get("min_semantic_score") or 0.45))
        )
        params.setdefault("grep_patterns", [])
        params.setdefault("file_pattern", "")
        params.setdefault("include_venv", False)
        if params.get("grep_sync_max_wall_seconds") is not None:
            params["grep_sync_max_wall_seconds"] = max(
                5.0,
                min(600.0, float(params["grep_sync_max_wall_seconds"])),
            )
        if params.get("grep_hard_timeout_seconds") is not None:
            params["grep_hard_timeout_seconds"] = clamp_hard_timeout_seconds(
                params["grep_hard_timeout_seconds"]
            )
        grep_scope = str(params.get("grep_scope") or "index_gap")
        if grep_scope not in ("index_gap", "all", "changed", "draft_only"):
            from ..core.exceptions import ValidationError

            raise ValidationError(
                "grep_scope must be index_gap, all, changed, or draft_only",
                field="grep_scope",
            )
        source = str(params.get("source") or "disk")
        if (
            source in ("draft_session", "both")
            and not str(params.get("session_id") or "").strip()
        ):
            from ..core.exceptions import ValidationError

            raise ValidationError(
                "session_id is required when source includes draft_session",
                field="session_id",
            )
        if params.get("require_structural_grep", True) and params.get("fast_text_only"):
            from ..core.exceptions import ValidationError

            raise ValidationError(
                "fast_text_only is not allowed when require_structural_grep=true",
                field="fast_text_only",
            )
        if params.get("inline_timeout_seconds") is not None:
            params["inline_timeout_seconds"] = resolve_inline_timeout_seconds(
                params["inline_timeout_seconds"]
            )
        return params

    async def execute(
        self,
        project_id: str,
        query: str,
        grep_patterns: Optional[List[str]] = None,
        file_pattern: str = "",
        entity_type: Optional[str] = None,
        mode: str = "intersection",
        profile: str = "generic",
        limit: int = 20,
        semantic_limit: int = 30,
        fulltext_limit: int = 30,
        grep_limit: int = 200,
        min_semantic_score: float = 0.45,
        case_sensitive: bool = False,
        literal: bool = True,
        include_docs: bool = True,
        include_tests: bool = True,
        include_hidden: bool = False,
        include_venv: bool = False,
        grep_sync_max_wall_seconds: Optional[float] = None,
        grep_hard_timeout_seconds: Optional[float] = None,
        grep_scope: str = "index_gap",
        scan_all: bool = False,
        source: str = "disk",
        session_id: Optional[str] = None,
        require_structural_grep: bool = True,
        debug: bool = False,
        fast_text_only: bool = False,
        auto_queue_on_inline_timeout: bool = True,
        inline_timeout_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        context = kwargs.get("context") or {}
        if not isinstance(context, dict):
            context = {}
        enqueue_params = {
            k: v
            for k, v in {
                "project_id": project_id,
                "query": query,
                "grep_patterns": grep_patterns,
                "file_pattern": file_pattern,
                "entity_type": entity_type,
                "mode": mode,
                "profile": profile,
                "limit": limit,
                "semantic_limit": semantic_limit,
                "fulltext_limit": fulltext_limit,
                "grep_limit": grep_limit,
                "min_semantic_score": min_semantic_score,
                "case_sensitive": case_sensitive,
                "literal": literal,
                "include_docs": include_docs,
                "include_tests": include_tests,
                "include_hidden": include_hidden,
                "include_venv": include_venv,
                "grep_sync_max_wall_seconds": grep_sync_max_wall_seconds,
                "grep_hard_timeout_seconds": grep_hard_timeout_seconds,
                "grep_scope": grep_scope,
                "scan_all": scan_all,
                "source": source,
                "session_id": session_id,
                "require_structural_grep": require_structural_grep,
                "debug": debug,
                "fast_text_only": fast_text_only,
                "auto_queue_on_inline_timeout": auto_queue_on_inline_timeout,
                "inline_timeout_seconds": inline_timeout_seconds,
            }.items()
            if v is not None
        }

        async def _run() -> SuccessResult | ErrorResult:
            return await self._execute_project_cross_search(
                project_id=project_id,
                query=query,
                grep_patterns=grep_patterns,
                file_pattern=file_pattern,
                entity_type=entity_type,
                mode=mode,
                profile=profile,
                limit=limit,
                semantic_limit=semantic_limit,
                fulltext_limit=fulltext_limit,
                grep_limit=grep_limit,
                min_semantic_score=min_semantic_score,
                case_sensitive=case_sensitive,
                literal=literal,
                include_docs=include_docs,
                include_tests=include_tests,
                include_hidden=include_hidden,
                include_venv=include_venv,
                grep_sync_max_wall_seconds=grep_sync_max_wall_seconds,
                grep_hard_timeout_seconds=grep_hard_timeout_seconds,
                grep_scope=grep_scope,
                scan_all=scan_all,
                source=source,
                session_id=session_id,
                require_structural_grep=require_structural_grep,
                debug=debug,
                fast_text_only=fast_text_only,
                context=context,
            )

        return await run_search_inline_or_queue(
            command_name=self.name,
            params=enqueue_params,
            context=context,
            auto_queue_on_inline_timeout=auto_queue_on_inline_timeout,
            inline_timeout_seconds=inline_timeout_seconds,
            execute_fn=_run,
        )

    async def _execute_project_cross_search(
        self,
        *,
        project_id: str,
        query: str,
        grep_patterns: Optional[List[str]],
        file_pattern: str,
        entity_type: Optional[str],
        mode: str,
        profile: str,
        limit: int,
        semantic_limit: int,
        fulltext_limit: int,
        grep_limit: int,
        min_semantic_score: float,
        case_sensitive: bool,
        literal: bool,
        include_docs: bool,
        include_tests: bool,
        include_hidden: bool,
        include_venv: bool,
        grep_sync_max_wall_seconds: Optional[float],
        grep_hard_timeout_seconds: Optional[float],
        grep_scope: str,
        scan_all: bool,
        source: str,
        session_id: Optional[str],
        require_structural_grep: bool,
        debug: bool,
        fast_text_only: bool,
        context: Dict[str, Any],
    ) -> SuccessResult | ErrorResult:
        warnings: List[Dict[str, Any]] = []
        successes = 0
        in_queue = is_queued_search_execution(context=context)

        try:
            project_root = self._resolve_project_root(project_id).resolve()
        except Exception as e:
            return self._handle_error(e, "PROJECT_NOT_FOUND", "project_cross_search")

        explicit_patterns = list(grep_patterns or [])
        final_patterns, derived_patterns = build_grep_pattern_list(
            query, explicit_patterns, profile  # type: ignore[arg-type]
        )
        plan = SearchPlan(
            semantic_limit=semantic_limit,
            fulltext_limit=fulltext_limit,
            grep_limit=grep_limit,
            grep_patterns=final_patterns,
            derived_grep_patterns=derived_patterns,
            file_pattern=file_pattern or "",
            entity_type=entity_type,
            mode=mode,  # type: ignore[arg-type]
            profile=profile,  # type: ignore[arg-type]
            limit=limit,
            min_semantic_score=min_semantic_score,
            case_sensitive=case_sensitive,
            literal=literal,
        )
        path_filters = PathFilterOptions(
            include_docs=include_docs,
            include_tests=include_tests,
            include_hidden=include_hidden,
            include_venv=include_venv,
            file_pattern=plan.file_pattern,
        )

        semantic_norm: List[Dict[str, Any]] = []
        fulltext_norm: List[Dict[str, Any]] = []
        grep_norm: List[Dict[str, Any]] = []

        if semantic_limit > 0:
            try:
                sem_cmd = SemanticSearchMCPCommand()
                sem_result = await sem_cmd.execute(
                    project_id=project_id,
                    query=query,
                    limit=min(semantic_limit, 100),
                    min_score=min_semantic_score,
                )
                if isinstance(sem_result, ErrorResult):
                    warnings.append(
                        {
                            "source": "semantic",
                            "code": getattr(sem_result, "code", None)
                            or "SEMANTIC_ERROR",
                            "message": str(getattr(sem_result, "message", sem_result)),
                        }
                    )
                else:
                    successes += 1
                    for row in (sem_result.data or {}).get("results") or []:
                        if not isinstance(row, dict):
                            continue
                        try:
                            hit = normalize_semantic_hit(row, project_root)
                        except Exception as row_err:
                            warnings.append(
                                {
                                    "source": "semantic",
                                    "code": "SEMANTIC_ROW_ERROR",
                                    "message": str(row_err),
                                }
                            )
                            continue
                        if hit.get("file_path"):
                            semantic_norm.append(hit)
            except Exception as e:
                warnings.append(
                    {
                        "source": "semantic",
                        "code": "SEMANTIC_ERROR",
                        "message": str(e),
                    }
                )

        database = None
        if fulltext_limit > 0:
            try:
                database = self._open_database_from_config(auto_analyze=False)
                search_cmd = SearchCommand(database, project_id)
                ft_rows = search_cmd.full_text_search(
                    query, entity_type=entity_type, limit=fulltext_limit
                )
                successes += 1
                for row in ft_rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        hit = normalize_fulltext_hit(row, project_root)
                    except Exception as row_err:
                        warnings.append(
                            {
                                "source": "fulltext",
                                "code": "FULLTEXT_ROW_ERROR",
                                "message": str(row_err),
                            }
                        )
                        continue
                    if hit.get("file_path"):
                        fulltext_norm.append(hit)
            except Exception as e:
                warnings.append(
                    {
                        "source": "fulltext",
                        "code": "FULLTEXT_ERROR",
                        "message": str(e),
                    }
                )
            finally:
                if database is not None:
                    database.disconnect()
                    database = None

        grep_limits = limits_for_queued_job() if in_queue else limits_for_sync()
        if not in_queue and grep_sync_max_wall_seconds is not None:
            grep_limits.max_wall_seconds = float(grep_sync_max_wall_seconds)
        grep_budget = GrepBudgetState(limits=grep_limits)
        grep_budget.usage.patterns_total = len(final_patterns)
        grep_line_only_diag: List[Dict[str, Any]] = []

        grep_hard_limit = resolve_hard_timeout_seconds(
            explicit=grep_hard_timeout_seconds,
            in_queue=in_queue,
        )
        if grep_limit > 0 and final_patterns:
            if grep_scope == "draft_only":
                grep_source = "draft_session"
            else:
                grep_source = source
            skip_indexed = grep_scope == "index_gap"
            indexed_only = grep_scope == "changed"
            try:
                grep_ok, grep_norm, grep_warnings = await asyncio.wait_for(
                    self._run_grep_phase(
                        project_id=project_id,
                        patterns=final_patterns,
                        project_root=project_root,
                        plan=plan,
                        grep_limit=grep_limit,
                        literal=literal,
                        case_sensitive=case_sensitive,
                        include_venv=include_venv,
                        include_hidden=include_hidden,
                        budget=grep_budget,
                        grep_scope=grep_scope,
                        scan_all=scan_all,
                        source=grep_source,
                        session_id=session_id,
                        skip_indexed_unchanged=skip_indexed,
                        indexed_only=indexed_only,
                        fast_text_only=fast_text_only,
                        grep_hard_timeout_seconds=grep_hard_limit,
                        context=context,
                    ),
                    timeout=grep_hard_limit,
                )
            except asyncio.TimeoutError:
                grep_ok = False
                grep_norm = []
                grep_warnings = [
                    {
                        "source": "grep",
                        "code": GREP_HARD_TIMEOUT,
                        "message": (
                            "Grep exceeded hard timeout and was stopped. Results may be "
                            "partial or absent."
                        ),
                        "hard_timeout_seconds": grep_hard_limit,
                    }
                ]
                grep_budget.mark_exceeded("grep_hard_timeout")
            warnings.extend(grep_warnings)
            if require_structural_grep:
                grep_structural, grep_line_only_diag, ignored_n = (
                    partition_grep_for_cross_search(grep_norm, require_structural=True)
                )
                if ignored_n > 0:
                    warnings.append(
                        {
                            "source": "grep",
                            "code": GREP_LINE_ONLY_IGNORED,
                            "message": (
                                "Grep returned line-only matches; ignored as cross-search "
                                "evidence because structural grep evidence is required."
                            ),
                            "ignored_count": ignored_n,
                        }
                    )
                grep_norm = grep_structural
            if grep_ok:
                successes += 1
        grep_budget.finalize_wall_clock()
        execution_mode: ExecutionMode = resolve_execution_mode(
            in_queue=in_queue,
            budget=grep_budget,
            pattern_count=len(final_patterns),
        )

        if successes == 0:
            first = warnings[0] if warnings else {}
            return ErrorResult(
                message=first.get("message") or "All search sources failed",
                code="CROSS_SEARCH_ERROR",
                details={
                    "warnings": warnings,
                    "upstream_code": first.get("code"),
                },
            )

        try:
            all_candidates, results, source_counts = merge_evidence(
                semantic_norm,
                fulltext_norm,
                grep_norm,
                path_filters=path_filters,
                mode=plan.mode,
                limit=plan.limit,
            )
        except Exception as e:
            logger.exception("project_cross_search merge failed: %s", e)
            return ErrorResult(
                message=str(e),
                code="CROSS_SEARCH_ERROR",
                details={"warnings": warnings, "phase": "merge"},
            )

        registered_commands: Optional[Set[str]] = None
        if profile == "command_audit":
            registered_commands = self._load_registered_command_names(project_root)
            for cand in results:
                try:
                    cand["command_audit"] = build_command_audit(
                        cand["file_path"],
                        cand["evidence"].get("grep") or [],
                        registered_commands=registered_commands,
                    )
                except Exception as e:
                    warnings.append(
                        {
                            "source": "merge",
                            "code": "COMMAND_AUDIT_ERROR",
                            "message": str(e),
                            "file_path": cand.get("file_path"),
                        }
                    )

        summary = build_summary(
            all_candidates,
            results,
            source_counts,
            profile=plan.profile,
            warnings=warnings,
        )

        payload: Dict[str, Any] = {
            "success": True,
            "query": query,
            "project_id": project_id,
            "mode": mode,
            "profile": profile,
            "execution_mode": execution_mode,
            "grep_budget": {
                "limits": grep_budget.limits.as_dict(),
                "usage": grep_budget.usage.as_dict(),
            },
            "warnings": list(warnings),
            "search_plan": {
                "semantic_limit": semantic_limit,
                "fulltext_limit": fulltext_limit,
                "grep_limit": grep_limit,
                "grep_hard_timeout_seconds": grep_hard_limit,
                "grep_patterns": final_patterns,
                "derived_grep_patterns": derived_patterns,
                "file_pattern": plan.file_pattern,
            },
            "results": results,
            "summary": summary,
            "require_structural_grep": require_structural_grep,
        }
        if debug and grep_line_only_diag:
            payload["diagnostics"] = {"grep_line_only": grep_line_only_diag}
        if execution_mode == "queued_recommended":
            payload["use_queue_recommended"] = True
        trim_payload_to_budget(payload, grep_budget.limits, grep_budget.usage, warnings)
        payload["warnings"] = list(warnings)
        payload["grep_budget"]["usage"] = grep_budget.usage.as_dict()

        return SuccessResult(data=payload)

    async def _run_grep_phase(
        self,
        *,
        project_id: str,
        patterns: List[str],
        project_root: Path,
        plan: SearchPlan,
        grep_limit: int,
        literal: bool,
        case_sensitive: bool,
        include_venv: bool,
        include_hidden: bool,
        budget: GrepBudgetState,
        grep_scope: str = "index_gap",
        scan_all: bool = False,
        source: str = "disk",
        session_id: Optional[str] = None,
        skip_indexed_unchanged: bool = True,
        indexed_only: bool = False,
        fast_text_only: bool = False,
        grep_hard_timeout_seconds: float = 120.0,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run fs_grep for each pattern with shared budget; never block the event loop."""
        grep_cmd = FsGrepCommand()
        per_pattern_limit = max(1, grep_limit // max(1, len(patterns)))
        grep_norm: List[Dict[str, Any]] = []
        grep_warnings: List[Dict[str, Any]] = []
        grep_ok = False
        last_pattern: Optional[str] = None
        grep_phase_started = time.monotonic()

        for pattern in patterns:
            last_pattern = pattern
            if budget.should_stop_grep_loop():
                break
            remaining_hard = grep_hard_timeout_seconds - (
                time.monotonic() - grep_phase_started
            )
            if remaining_hard <= 0:
                budget.mark_exceeded("grep_hard_timeout")
                grep_warnings.append(
                    {
                        "source": "grep",
                        "code": GREP_HARD_TIMEOUT,
                        "message": (
                            "Grep exceeded hard timeout and was stopped. Results may be "
                            "partial or absent."
                        ),
                        "hard_timeout_seconds": grep_hard_timeout_seconds,
                        "pattern": pattern,
                    }
                )
                break
            per_limits = budget.per_pattern_limits(per_pattern_limit)
            wall_budget = per_limits.get("wall_time_budget_s")
            per_hard = min(
                remaining_hard,
                float(wall_budget) if wall_budget is not None else remaining_hard,
            )
            try:
                grep_result = await grep_cmd.execute(
                    project_id=project_id,
                    pattern=pattern,
                    literal=literal,
                    case_sensitive=case_sensitive,
                    file_pattern=plan.file_pattern or None,
                    max_matches=int(per_limits["max_matches"]),
                    max_files_scanned=int(per_limits["max_files_scanned"]),
                    wall_time_budget_s=(
                        float(wall_budget) if wall_budget is not None else None
                    ),
                    hard_timeout_seconds=per_hard,
                    fast_text_only=fast_text_only,
                    enrich_blocks=not fast_text_only,
                    enrich_max_results=min(50, int(per_limits["max_matches"])),
                    ensure_persisted_tree=True,
                    stable_ids_required=True,
                    scan_all=scan_all,
                    source=source,
                    session_id=session_id,
                    skip_indexed_unchanged=skip_indexed_unchanged,
                    indexed_only=indexed_only,
                    show_venv=include_venv,
                    show_hidden=include_hidden,
                    auto_queue_on_inline_timeout=False,
                    context=context or {},
                )
            except asyncio.TimeoutError:
                budget.mark_exceeded("grep_hard_timeout")
                grep_warnings.append(
                    {
                        "source": "grep",
                        "code": GREP_HARD_TIMEOUT,
                        "message": (
                            "Grep exceeded hard timeout and was stopped. Results may be "
                            "partial or absent."
                        ),
                        "hard_timeout_seconds": grep_hard_timeout_seconds,
                        "pattern": pattern,
                    }
                )
                break
            except Exception as e:
                grep_warnings.append(
                    {
                        "source": "grep",
                        "code": "GREP_ERROR",
                        "message": str(e),
                        "pattern": pattern,
                    }
                )
                continue

            if isinstance(grep_result, ErrorResult):
                err_code = getattr(grep_result, "code", None) or "GREP_ERROR"
                grep_warnings.append(
                    {
                        "source": "grep",
                        "code": err_code,
                        "message": str(getattr(grep_result, "message", grep_result)),
                        "pattern": pattern,
                        "details": getattr(grep_result, "details", None),
                    }
                )
                if err_code == GREP_HARD_TIMEOUT:
                    budget.mark_exceeded("grep_hard_timeout")
                    break
                continue

            grep_data = grep_result.data or {}
            budget.record_pattern_result(grep_data)
            if grep_data.get("budget_exceeded"):
                grep_warnings.append(budget.budget_warning(pattern))

            grep_ok = True
            for row in grep_data.get("matches") or []:
                if not isinstance(row, dict):
                    continue
                try:
                    hit = normalize_grep_hit(row, pattern, project_root)
                except Exception as row_err:
                    grep_warnings.append(
                        {
                            "source": "grep",
                            "code": "GREP_ROW_ERROR",
                            "message": str(row_err),
                            "pattern": pattern,
                        }
                    )
                    continue
                if hit.get("file_path"):
                    grep_norm.append(hit)
            if budget.should_stop_grep_loop():
                break

        if budget.usage.exceeded and last_pattern is not None:
            grep_warnings.append(budget.budget_warning(last_pattern))

        return grep_ok, grep_norm, grep_warnings

    def _load_registered_command_names(self, project_root: Path) -> Set[str]:
        """Best-effort scan of hooks.py for registered command names."""
        names: Set[str] = set()
        hooks_path = project_root / "code_analysis" / "hooks_register_part1.py"
        if not hooks_path.is_file():
            return names
        try:
            text = hooks_path.read_text(encoding="utf-8")
        except OSError:
            return names
        for line in text.splitlines():
            if "reg.register(" not in line:
                continue
            # reg.register(FooCommand, "custom") — class name heuristic only
            chunk = line.split("reg.register(", 1)[-1].split(",", 1)[0].strip()
            if chunk.endswith("Command"):
                stem = chunk[: -len("Command")]
                if stem:
                    import re

                    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", stem).lower()
                    names.add(snake)
        return names

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Orchestrates semantic_search, fulltext_search, and fs_grep without replacing "
                "them. Normalizes hits to project-relative file paths, groups evidence by file, "
                "computes evidence_score (count of independent sources) and confidence "
                "(high/medium/low), and applies union/intersection/strict or source-first modes. "
                "Use explicit grep_patterns for audits; derived patterns from natural-language "
                "queries are weak evidence. The command_audit profile adds session-guard markers "
                "and summary fields for MCP command coverage review."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID from list_projects.",
                    "type": "string",
                    "required": True,
                },
                "query": {
                    "description": "Shared query for semantic and full-text backends.",
                    "type": "string",
                    "required": True,
                },
                "grep_patterns": {
                    "description": "Explicit fs_grep patterns; preferred over auto-derived markers.",
                    "type": "array",
                    "required": False,
                    "default": [],
                },
                "mode": {
                    "description": "Filtering mode: union, intersection, strict, or source-first.",
                    "type": "string",
                    "required": False,
                    "default": "intersection",
                    "enum": list(MODES),
                },
                "profile": {
                    "description": "generic or command_audit preset.",
                    "type": "string",
                    "required": False,
                    "default": "generic",
                    "enum": list(PROFILES),
                },
                "limit": {
                    "description": "Maximum merged file candidates returned.",
                    "type": "integer",
                    "required": False,
                    "default": 20,
                },
            },
            "return_value": {
                "success": {
                    "description": "Merged evidence map grouped by file_path.",
                    "data": {
                        "results": "Ranked candidates with sources, evidence arrays, confidence.",
                        "summary": "Counts, source_counts, optional command_audit_summary.",
                        "search_plan": "Effective limits and grep patterns used.",
                    },
                    "example": {
                        "success": True,
                        "query": "session_create",
                        "results": [],
                        "summary": {"returned": 0, "source_counts": {}},
                    },
                },
                "error": {
                    "description": "All sources failed or validation error.",
                    "code": "CROSS_SEARCH_ERROR",
                    "message": "Human-readable message",
                },
            },
            "usage_examples": [
                {
                    "description": "Find session_create via fulltext + grep intersection",
                    "command": {
                        "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "query": "session_create",
                        "grep_patterns": ["session_create"],
                        "mode": "intersection",
                        "limit": 10,
                    },
                    "explanation": (
                        "Requires at least two sources to agree on file_path; "
                        "explicit grep_patterns give strong filesystem evidence."
                    ),
                },
                {
                    "description": "Command audit profile for session guard coverage",
                    "command": {
                        "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "query": "MCP commands requiring registered client session",
                        "profile": "command_audit",
                        "mode": "union",
                        "file_pattern": "code_analysis/commands",
                        "limit": 50,
                    },
                    "explanation": (
                        "Expands grep markers and attaches command_audit blocks per command file."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "project_id does not resolve to a project root.",
                    "message": "Project not found: {project_id}",
                    "solution": "Call list_projects and retry with a valid project_id.",
                },
                "INVALID_QUERY": {
                    "description": "query is empty after strip.",
                    "message": "query must be non-empty",
                    "solution": "Provide a non-empty search query.",
                },
                "INVALID_MODE": {
                    "description": "mode is not a supported enum value.",
                    "message": "mode must be one of [...]",
                    "solution": "Use union, intersection, strict, or a source-first mode.",
                },
                "CROSS_SEARCH_ERROR": {
                    "description": "Every search source failed.",
                    "message": "All search sources failed",
                    "solution": (
                        "Check indexes/embeddings, database connectivity, and grep patterns; "
                        "see summary.warnings for per-source errors."
                    ),
                },
                "GREP_BUDGET_EXCEEDED": {
                    "description": (
                        "Sync grep scan hit wall-time, file, match, or response-size limits."
                    ),
                    "message": "Grep scan stopped early to keep the server responsive.",
                    "solution": (
                        "Retry with call_server(..., use_queue=true) and poll "
                        "queue_get_job_status until result.command.result.success is true."
                    ),
                },
                "GREP_HARD_TIMEOUT": {
                    "description": (
                        "Grep phase exceeded grep_hard_timeout_seconds and was stopped."
                    ),
                    "message": "Grep exceeded hard timeout and was stopped.",
                    "solution": (
                        "Increase grep_hard_timeout_seconds, narrow grep_patterns, or disable "
                        "unused sources with semantic_limit=0 and fulltext_limit=0."
                    ),
                },
                "FAST_TEXT_ONLY_CONFLICT": {
                    "description": (
                        "fast_text_only=true cannot be used with require_structural_grep=true."
                    ),
                    "message": "fast_text_only is not allowed when require_structural_grep=true",
                    "solution": (
                        "Set require_structural_grep=false or omit fast_text_only."
                    ),
                },
            },
            "best_practices": [
                "Prefer explicit grep_patterns for audits; derived patterns are weak evidence.",
                "Use intersection or strict mode when you need corroboration across sources.",
                "Semantic-only hits are low confidence — verify with universal_file_preview.",
                "Grep-only hits are exact traces — preview the file before acting.",
                "Keep include_venv=false unless you intentionally scan virtualenv trees.",
                "Heavy grep-only audits: use_queue=true (command default supports queue).",
                "Sync calls enforce grep_budget; check execution_mode and warnings in the response.",
            ],
        }
