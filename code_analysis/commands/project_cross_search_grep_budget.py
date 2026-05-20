"""
Grep scan budgets for project_cross_search (sync vs queued execution).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

GREP_BUDGET_EXCEEDED = "GREP_BUDGET_EXCEEDED"
ExecutionMode = Literal["sync", "queued_recommended", "queued"]

# Sync path: keep HTTP handler responsive; one slow pattern must not block the server.
SYNC_MAX_WALL_SECONDS = 90.0
SYNC_MAX_FILES_PER_PATTERN = 150
SYNC_MAX_FILES_TOTAL = 400
SYNC_MAX_MATCHES_PER_PATTERN = 50
SYNC_MAX_TOTAL_MATCHES = 300
SYNC_MAX_RESPONSE_BYTES = 2_000_000

# Queued worker: allow full scan (still bounded to avoid runaway jobs).
QUEUED_MAX_WALL_SECONDS = 3600.0
QUEUED_MAX_FILES_PER_PATTERN = 10_000
QUEUED_MAX_FILES_TOTAL = 50_000
QUEUED_MAX_MATCHES_PER_PATTERN = 2000
QUEUED_MAX_TOTAL_MATCHES = 10_000
QUEUED_MAX_RESPONSE_BYTES = 8_000_000


@dataclass
class GrepBudgetLimits:
    """Effective limits for one project_cross_search invocation."""

    mode: Literal["sync", "full"]
    max_wall_seconds: float
    max_files_per_pattern: int
    max_files_total: int
    max_matches_per_pattern: int
    max_total_matches: int
    max_response_bytes: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "max_wall_seconds": self.max_wall_seconds,
            "max_files_per_pattern": self.max_files_per_pattern,
            "max_files_total": self.max_files_total,
            "max_matches_per_pattern": self.max_matches_per_pattern,
            "max_total_matches": self.max_total_matches,
            "max_response_bytes": self.max_response_bytes,
        }


@dataclass
class GrepBudgetUsage:
    """Observed grep cost during execution."""

    wall_seconds: float = 0.0
    files_scanned: int = 0
    grep_matches: int = 0
    patterns_completed: int = 0
    patterns_total: int = 0
    response_bytes: int = 0
    exceeded: bool = False
    exceed_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "wall_seconds": round(self.wall_seconds, 3),
            "files_scanned": self.files_scanned,
            "grep_matches": self.grep_matches,
            "patterns_completed": self.patterns_completed,
            "patterns_total": self.patterns_total,
            "response_bytes": self.response_bytes,
            "exceeded": self.exceeded,
            "exceed_reason": self.exceed_reason,
        }


@dataclass
class GrepBudgetState:
    """Mutable budget tracker across multiple fs_grep calls."""

    limits: GrepBudgetLimits
    usage: GrepBudgetUsage = field(default_factory=GrepBudgetUsage)
    _grep_started_at: float = field(default_factory=time.monotonic)

    def remaining_wall_seconds(self) -> float:
        elapsed = time.monotonic() - self._grep_started_at
        return max(0.0, self.limits.max_wall_seconds - elapsed)

    def remaining_files_total(self) -> int:
        return max(0, self.limits.max_files_total - self.usage.files_scanned)

    def remaining_total_matches(self) -> int:
        return max(0, self.limits.max_total_matches - self.usage.grep_matches)

    def mark_exceeded(self, reason: str) -> None:
        self.usage.exceeded = True
        self.usage.exceed_reason = reason

    def should_stop_grep_loop(self) -> bool:
        if self.usage.exceeded:
            return True
        if self.remaining_wall_seconds() <= 0:
            self.mark_exceeded("max_wall_seconds")
            return True
        if self.usage.files_scanned >= self.limits.max_files_total:
            self.mark_exceeded("max_files_total")
            return True
        if self.usage.grep_matches >= self.limits.max_total_matches:
            self.mark_exceeded("max_total_matches")
            return True
        return False

    def per_pattern_limits(self, per_pattern_limit: int) -> Dict[str, Any]:
        return {
            "max_files_scanned": min(
                self.limits.max_files_per_pattern,
                self.remaining_files_total(),
            ),
            "wall_time_budget_s": self.remaining_wall_seconds(),
            "max_matches": min(
                per_pattern_limit,
                self.limits.max_matches_per_pattern,
                self.remaining_total_matches(),
            ),
        }

    def record_pattern_result(self, grep_data: Dict[str, Any]) -> None:
        self.usage.patterns_completed += 1
        self.usage.files_scanned += int(grep_data.get("files_scanned") or 0)
        self.usage.grep_matches += int(grep_data.get("match_count") or 0)
        if grep_data.get("budget_exceeded"):
            self.mark_exceeded(str(grep_data.get("budget_reason") or "pattern_budget"))

    def finalize_wall_clock(self) -> None:
        self.usage.wall_seconds = time.monotonic() - self._grep_started_at

    def budget_warning(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        msg = (
            "Grep scan stopped early to keep the server responsive. "
            "Retry with use_queue=true for a full filesystem scan."
        )
        warn: Dict[str, Any] = {
            "source": "grep",
            "code": GREP_BUDGET_EXCEEDED,
            "message": msg,
            "suggestion": "call_server(..., use_queue=true) and poll queue_get_job_status",
        }
        if pattern is not None:
            warn["pattern"] = pattern
        if self.usage.exceed_reason:
            warn["reason"] = self.usage.exceed_reason
        return warn


def limits_for_queued_job() -> GrepBudgetLimits:
    return GrepBudgetLimits(
        mode="full",
        max_wall_seconds=QUEUED_MAX_WALL_SECONDS,
        max_files_per_pattern=QUEUED_MAX_FILES_PER_PATTERN,
        max_files_total=QUEUED_MAX_FILES_TOTAL,
        max_matches_per_pattern=QUEUED_MAX_MATCHES_PER_PATTERN,
        max_total_matches=QUEUED_MAX_TOTAL_MATCHES,
        max_response_bytes=QUEUED_MAX_RESPONSE_BYTES,
    )


def limits_for_sync() -> GrepBudgetLimits:
    return GrepBudgetLimits(
        mode="sync",
        max_wall_seconds=SYNC_MAX_WALL_SECONDS,
        max_files_per_pattern=SYNC_MAX_FILES_PER_PATTERN,
        max_files_total=SYNC_MAX_FILES_TOTAL,
        max_matches_per_pattern=SYNC_MAX_MATCHES_PER_PATTERN,
        max_total_matches=SYNC_MAX_TOTAL_MATCHES,
        max_response_bytes=SYNC_MAX_RESPONSE_BYTES,
    )


def resolve_execution_mode(
    *,
    in_queue: bool,
    budget: GrepBudgetState,
    pattern_count: int,
) -> ExecutionMode:
    if in_queue:
        return "queued"
    if budget.usage.exceeded or pattern_count > 6:
        return "queued_recommended"
    return "sync"


def estimate_json_bytes(payload: Any) -> int:
    try:
        return len(json.dumps(payload, default=str).encode("utf-8"))
    except Exception:
        return 0


def trim_payload_to_budget(
    data: Dict[str, Any],
    limits: GrepBudgetLimits,
    usage: GrepBudgetUsage,
    warnings: List[Dict[str, Any]],
) -> None:
    """Truncate merged results if serialized response would exceed max_response_bytes."""
    size = estimate_json_bytes(data)
    usage.response_bytes = size
    if size <= limits.max_response_bytes:
        return
    results = data.get("results")
    if not isinstance(results, list) or not results:
        usage.mark_exceeded("max_response_bytes")
        warnings.append(
            {
                "source": "merge",
                "code": GREP_BUDGET_EXCEEDED,
                "message": (
                    f"Response size {size} bytes exceeds budget "
                    f"{limits.max_response_bytes}; retry with use_queue=true."
                ),
                "suggestion": "call_server(..., use_queue=true)",
            }
        )
        return
    trimmed: List[Any] = []
    for row in results:
        trimmed.append(row)
        data["results"] = trimmed
        size = estimate_json_bytes(data)
        if size > limits.max_response_bytes:
            trimmed.pop()
            data["results"] = trimmed
            data["summary"]["returned"] = len(trimmed)
            data["summary"]["truncated_for_response_budget"] = True
            usage.mark_exceeded("max_response_bytes")
            warnings.append(
                {
                    "source": "merge",
                    "code": GREP_BUDGET_EXCEEDED,
                    "message": (
                        "Merged results truncated to fit sync response size budget. "
                        "Use use_queue=true for the full result set."
                    ),
                    "suggestion": "call_server(..., use_queue=true)",
                }
            )
            usage.response_bytes = estimate_json_bytes(data)
            return
    usage.response_bytes = size
