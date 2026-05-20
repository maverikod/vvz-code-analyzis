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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.progress_tracker import get_progress_tracker_from_context
from .base_mcp_command import BaseMCPCommand
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
)
from .search import SearchCommand
from .semantic_search_mcp import SemanticSearchMCPCommand

logger = logging.getLogger(__name__)


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
        },
    }


class ProjectCrossSearchCommand(BaseMCPCommand):
    """Run semantic, full-text, and grep search; merge evidence by file path."""

    name = "project_cross_search"
    version = "1.0.0"
    descr = (
        "Cross-search orchestrator combining semantic_search, fulltext_search, and fs_grep "
        "into ranked evidence grouped by file path with confidence labels."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

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

        params["limit"] = max(1, min(200, int(params.get("limit") or 20)))
        params["semantic_limit"] = max(
            0, min(200, int(params.get("semantic_limit") or 30))
        )
        params["fulltext_limit"] = max(
            0, min(200, int(params.get("fulltext_limit") or 30))
        )
        params["grep_limit"] = max(0, min(2000, int(params.get("grep_limit") or 200)))
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
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        warnings: List[Dict[str, Any]] = []
        successes = 0
        context = kwargs.get("context") or {}
        in_queue = get_progress_tracker_from_context(context) is not None

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

        if grep_limit > 0 and final_patterns:
            grep_ok, grep_norm, grep_warnings = await self._run_grep_phase(
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
            )
            warnings.extend(grep_warnings)
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
                "grep_patterns": final_patterns,
                "derived_grep_patterns": derived_patterns,
                "file_pattern": plan.file_pattern,
            },
            "results": results,
            "summary": summary,
        }
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
    ) -> Tuple[bool, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run fs_grep for each pattern with shared budget; never block the event loop."""
        grep_cmd = FsGrepCommand()
        per_pattern_limit = max(1, grep_limit // max(1, len(patterns)))
        grep_norm: List[Dict[str, Any]] = []
        grep_warnings: List[Dict[str, Any]] = []
        grep_ok = False
        last_pattern: Optional[str] = None

        for pattern in patterns:
            last_pattern = pattern
            if budget.should_stop_grep_loop():
                break
            per_limits = budget.per_pattern_limits(per_pattern_limit)
            wall_budget = per_limits.get("wall_time_budget_s")
            try:
                grep_result = await asyncio.wait_for(
                    grep_cmd.execute(
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
                        fast_text_only=True,
                        enrich_blocks=False,
                        show_venv=include_venv,
                        show_hidden=include_hidden,
                    ),
                    timeout=max(
                        1.0, float(wall_budget or budget.limits.max_wall_seconds)
                    )
                    + 5.0,
                )
            except asyncio.TimeoutError:
                budget.mark_exceeded("pattern_wall_timeout")
                grep_warnings.append(
                    {
                        "source": "grep",
                        "code": GREP_BUDGET_EXCEEDED,
                        "message": f"Grep timed out for pattern {pattern!r}",
                        "pattern": pattern,
                        "suggestion": "call_server(..., use_queue=true)",
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
                grep_warnings.append(
                    {
                        "source": "grep",
                        "code": getattr(grep_result, "code", None) or "GREP_ERROR",
                        "message": str(getattr(grep_result, "message", grep_result)),
                        "pattern": pattern,
                    }
                )
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
