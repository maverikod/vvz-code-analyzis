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
import time
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.progress_tracker import get_progress_tracker_from_context
from .base_mcp_command import BaseMCPCommand
from .fs_grep_budget import (
    GREP_BUDGET_EXCEEDED,
    GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
    GREP_TIMEOUT,
    FsGrepBudgetState,
    cap_candidate_paths,
    limits_for_queue,
    limits_for_sync,
    resolve_execution_mode,
)
from .grep_block_resolver import GrepBlockResolver
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
    version = "1.3.0"
    descr = (
        "Search file contents on disk (grep-style). Does not use the database full-text index; "
        "use ``fulltext_search`` for indexed search. Respects the same walk rules as "
        "``list_project_files``. Sync calls enforce wall-time and file budgets; use "
        "``use_queue=true`` for full scans."
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

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
                },
                "line_preview_len": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Max characters returned per matching line. Default from server config."
                    ),
                    "nullable": True,
                },
                "fast_text_only": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Phase-1 text scan only (no CST/sidecar block resolver). Default true "
                        "for responsive sync grep."
                    ),
                },
                "enrich_blocks": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, run phase-2 structural enrichment (block_id/block_type) for "
                        "the first enrich_max_results matches only."
                    ),
                },
                "enrich_max_results": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 0,
                    "maximum": 200,
                    "description": "Max matches to enrich when enrich_blocks=true.",
                },
                "grep_sync_max_wall_seconds": {
                    "type": "number",
                    "minimum": 5,
                    "maximum": 600,
                    "description": (
                        "Sync-only total wall-time budget. Ignored when executed via job queue."
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
        params = super().validate_params(params)
        params["max_matches"] = max(
            1, min(10000, int(params.get("max_matches") or 500))
        )
        params["enrich_max_results"] = max(
            0, min(200, int(params.get("enrich_max_results") or 20))
        )
        if params.get("grep_sync_max_wall_seconds") is not None:
            params["grep_sync_max_wall_seconds"] = max(
                5.0,
                min(600.0, float(params["grep_sync_max_wall_seconds"])),
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
        fast_text_only: bool = True,
        enrich_blocks: bool = False,
        enrich_max_results: int = 20,
        grep_sync_max_wall_seconds: Optional[float] = None,
        show_venv: bool = False,
        python_only: bool = False,
        include_venv_ignore_exceptions: bool = False,
        show_hidden: bool = False,
        max_files_scanned: Optional[int] = None,
        wall_time_budget_s: Optional[float] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Run grep off the event loop; enforce sync wall-time via asyncio.wait_for."""
        context = kwargs.get("context") or {}
        in_queue = get_progress_tracker_from_context(context) is not None
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
                    fast_text_only,
                    enrich_blocks,
                    enrich_max_results,
                    show_venv,
                    python_only,
                    include_venv_ignore_exceptions,
                    show_hidden,
                    limits,
                    in_queue,
                    wall_budget,
                ),
                timeout=wall_budget + 15.0,
            )
        except asyncio.TimeoutError:
            return ErrorResult(
                message=(
                    "fs_grep exceeded sync wall-time budget; retry with use_queue=true"
                ),
                code=GREP_TIMEOUT,
                details={
                    "wall_time_budget_s": wall_budget,
                    "suggestion": "call_server(..., use_queue=true)",
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
        fast_text_only: bool,
        enrich_blocks: bool,
        enrich_max_results: int,
        show_venv: bool,
        python_only: bool,
        include_venv_ignore_exceptions: bool,
        show_hidden: bool,
        limits: Any,
        in_queue: bool,
        wall_budget: float,
    ) -> SuccessResult | ErrorResult:
        """Phase-1 fast text scan; optional phase-2 block enrichment."""
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
        effective_max_matches = min(max_matches, limits.max_matches)

        try:
            started_at = perf_counter()
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
            fs_paths = cap_candidate_paths(fs_paths, budget)

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

            matches, scan_stats = _phase1_text_scan(
                project_root=project_root,
                fs_paths=fs_paths,
                needle=needle,
                literal=literal,
                case_sensitive=case_sensitive,
                regex=regex,
                max_matches=effective_max_matches,
                max_file_bytes=max_file_bytes,
                line_preview_len=line_preview_len,
                budget=budget,
            )

            do_enrich = enrich_blocks and not fast_text_only
            if do_enrich and matches:
                _phase2_enrich_blocks(
                    project_root=project_root,
                    matches=matches,
                    enrich_max_results=enrich_max_results,
                    budget=budget,
                )
            elif enrich_blocks and fast_text_only and matches:
                budget.add_warning(
                    GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
                    "Structural enrichment skipped because fast_text_only=true.",
                    enrich_max_results=enrich_max_results,
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
            }
            if execution_mode == "queued_recommended":
                payload["use_queue_recommended"] = True

            _trim_response_payload(payload, budget)

            return SuccessResult(data=payload)
        except Exception as e:
            return self._handle_error(e, "FS_GREP_ERROR", "fs_grep")

    @classmethod
    def metadata(cls: type["FsGrepCommand"]) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Two-phase grep: phase-1 streams UTF-8 lines with ``fast_text_only=true`` "
                "(default, no CST/DB). Optional phase-2 ``enrich_blocks`` resolves block_id "
                "for the first ``enrich_max_results`` hits only. Sync calls enforce "
                "wall-time, scanned-file, and match budgets; heavy scans should use "
                "``use_queue=true`` (command class sets use_queue)."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID from create_project or list_projects.",
                    "type": "string",
                    "required": True,
                },
                "pattern": {
                    "description": "Literal substring or Python regular expression to search.",
                    "type": "string",
                    "required": True,
                },
                "fast_text_only": {
                    "description": "Skip structural block resolution during scan (default true).",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "enrich_blocks": {
                    "description": "Run phase-2 enrichment for first enrich_max_results matches.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "max_matches": {
                    "description": "Stop after this many matching lines.",
                    "type": "integer",
                    "required": False,
                    "default": 500,
                },
            },
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
                "Keep fast_text_only=true for broad sync grep.",
                "Use enrich_blocks only when you need block_id on a small result set.",
                "Heavy scans: call_server(..., use_queue=true) and poll queue_get_job_status.",
                "Narrow with file_pattern whenever possible.",
            ],
        }


def _phase1_text_scan(
    *,
    project_root: Any,
    fs_paths: List[Any],
    needle: str,
    literal: bool,
    case_sensitive: bool,
    regex: Optional[re.Pattern[str]],
    max_matches: int,
    max_file_bytes: int,
    line_preview_len: int,
    budget: FsGrepBudgetState,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    files_scanned = 0
    files_skipped_large = 0
    files_skipped_io = 0
    skipped_large_samples: List[Dict[str, Any]] = []

    for abs_path in fs_paths:
        if len(matches) >= max_matches:
            break
        if budget.should_stop_scan(
            matches_count=len(matches), files_scanned=files_scanned
        ):
            break

        rel = canonical_relative_path(project_root, abs_path)
        try:
            size = abs_path.stat().st_size
        except OSError:
            files_skipped_io += 1
            continue
        if max_file_bytes and size > max_file_bytes:
            files_skipped_large += 1
            if len(skipped_large_samples) < 20:
                skipped_large_samples.append({"relative_path": rel, "size_bytes": size})
            continue

        files_scanned += 1
        try:
            with abs_path.open("r", encoding="utf-8", errors="replace") as fh:
                for i, raw_line in enumerate(fh, start=1):
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
                        matches.append(
                            {
                                "relative_path": rel,
                                "line_number": i,
                                "line": line_text,
                                "block_id": None,
                                "block_type": None,
                            }
                        )
        except OSError:
            files_skipped_io += 1
            continue

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
) -> None:
    if enrich_max_results <= 0:
        budget.add_warning(
            GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
            "enrich_max_results=0; no structural enrichment performed.",
        )
        return

    resolver = GrepBlockResolver()
    try:
        limit = min(len(matches), enrich_max_results)
        for row in matches[:limit]:
            if budget.should_stop_scan(
                matches_count=len(matches),
                files_scanned=budget.usage.files_scanned,
            ):
                break
            abs_path = (project_root / row["relative_path"]).resolve()
            block_id, block_type = resolver.resolve(abs_path, int(row["line_number"]))
            row["block_id"] = block_id
            row["block_type"] = block_type
        if len(matches) > enrich_max_results:
            budget.add_warning(
                GREP_STRUCTURAL_ENRICHMENT_SKIPPED,
                (
                    f"Structural enrichment applied to first {enrich_max_results} "
                    f"of {len(matches)} matches only."
                ),
                enrich_max_results=enrich_max_results,
                matches_total=len(matches),
            )
    finally:
        resolver.cleanup()


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
