"""
Sync and queued scan budgets for fs_grep.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

GREP_BUDGET_EXCEEDED = "GREP_BUDGET_EXCEEDED"
GREP_TIMEOUT = "GREP_TIMEOUT"
GREP_TOO_MANY_FILES = "GREP_TOO_MANY_FILES"
GREP_STRUCTURAL_ENRICHMENT_SKIPPED = "GREP_STRUCTURAL_ENRICHMENT_SKIPPED"

ExecutionMode = Literal["sync", "queued_recommended", "queued"]

# Sync: must return before proxy/client times out; block resolver off by default.
SYNC_MAX_WALL_SECONDS = 45.0
SYNC_MAX_FILES_SCANNED = 250
SYNC_MAX_CANDIDATE_FILES = 1500
SYNC_MAX_MATCHES_CAP = 500
SYNC_MAX_RESPONSE_BYTES = 2_000_000

QUEUED_MAX_WALL_SECONDS = 3600.0
QUEUED_MAX_FILES_SCANNED = 50_000
QUEUED_MAX_CANDIDATE_FILES = 500_000
QUEUED_MAX_MATCHES_CAP = 10_000
QUEUED_MAX_RESPONSE_BYTES = 8_000_000


@dataclass
class FsGrepBudgetLimits:
    mode: Literal["sync", "full"]
    max_wall_seconds: float
    max_files_scanned: int
    max_candidate_files: int
    max_matches: int
    max_response_bytes: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "max_wall_seconds": self.max_wall_seconds,
            "max_files_scanned": self.max_files_scanned,
            "max_candidate_files": self.max_candidate_files,
            "max_matches": self.max_matches,
            "max_response_bytes": self.max_response_bytes,
        }


@dataclass
class FsGrepBudgetUsage:
    wall_seconds: float = 0.0
    candidate_files: int = 0
    files_scanned: int = 0
    matches_returned: int = 0
    budget_exceeded: bool = False
    exceed_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "wall_seconds": round(self.wall_seconds, 3),
            "candidate_files": self.candidate_files,
            "files_scanned": self.files_scanned,
            "matches_returned": self.matches_returned,
            "budget_exceeded": self.budget_exceeded,
            "exceed_reason": self.exceed_reason,
        }


@dataclass
class FsGrepBudgetState:
    limits: FsGrepBudgetLimits
    usage: FsGrepBudgetUsage = field(default_factory=FsGrepBudgetUsage)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    _started_at: float = field(default_factory=time.monotonic)

    def deadline(self) -> Optional[float]:
        return self._started_at + self.limits.max_wall_seconds

    def remaining_wall_seconds(self) -> float:
        end = self.deadline()
        if end is None:
            return self.limits.max_wall_seconds
        return max(0.0, end - time.monotonic())

    def mark_exceeded(self, reason: str) -> None:
        self.usage.budget_exceeded = True
        self.usage.exceed_reason = reason

    def should_stop_scan(self, *, matches_count: int, files_scanned: int) -> bool:
        if self.usage.budget_exceeded:
            return True
        if matches_count >= self.limits.max_matches:
            return False
        if files_scanned >= self.limits.max_files_scanned:
            self.mark_exceeded("max_files_scanned")
            return True
        end = self.deadline()
        if end is not None and time.monotonic() >= end:
            self.mark_exceeded("max_wall_seconds")
            return True
        return False

    def finalize(self) -> None:
        self.usage.wall_seconds = time.monotonic() - self._started_at

    def add_warning(self, code: str, message: str, **extra: Any) -> None:
        row: Dict[str, Any] = {"code": code, "message": message}
        row.update(extra)
        self.warnings.append(row)

    def budget_warning(self) -> Dict[str, Any]:
        return {
            "code": GREP_BUDGET_EXCEEDED,
            "message": (
                "Grep scan stopped early to keep the server responsive. "
                "Retry with use_queue=true for a full filesystem scan."
            ),
            "suggestion": "call_server(..., use_queue=true)",
            "reason": self.usage.exceed_reason,
        }


def limits_for_sync(
    *,
    max_matches: int,
    grep_sync_max_wall_seconds: Optional[float] = None,
) -> FsGrepBudgetLimits:
    wall = (
        float(grep_sync_max_wall_seconds)
        if grep_sync_max_wall_seconds is not None
        else SYNC_MAX_WALL_SECONDS
    )
    return FsGrepBudgetLimits(
        mode="sync",
        max_wall_seconds=max(5.0, min(600.0, wall)),
        max_files_scanned=SYNC_MAX_FILES_SCANNED,
        max_candidate_files=SYNC_MAX_CANDIDATE_FILES,
        max_matches=max(1, min(max_matches, SYNC_MAX_MATCHES_CAP)),
        max_response_bytes=SYNC_MAX_RESPONSE_BYTES,
    )


def limits_for_queue(*, max_matches: int) -> FsGrepBudgetLimits:
    return FsGrepBudgetLimits(
        mode="full",
        max_wall_seconds=QUEUED_MAX_WALL_SECONDS,
        max_files_scanned=QUEUED_MAX_FILES_SCANNED,
        max_candidate_files=QUEUED_MAX_CANDIDATE_FILES,
        max_matches=max(1, min(max_matches, QUEUED_MAX_MATCHES_CAP)),
        max_response_bytes=QUEUED_MAX_RESPONSE_BYTES,
    )


def resolve_execution_mode(
    *,
    in_queue: bool,
    budget: FsGrepBudgetState,
    candidate_files: int,
) -> ExecutionMode:
    if in_queue:
        return "queued"
    if budget.usage.budget_exceeded or candidate_files > SYNC_MAX_CANDIDATE_FILES:
        return "queued_recommended"
    return "sync"


def cap_candidate_paths(
    paths: List[Any],
    budget: FsGrepBudgetState,
) -> List[Any]:
    budget.usage.candidate_files = len(paths)
    if len(paths) <= budget.limits.max_candidate_files:
        return paths
    budget.add_warning(
        GREP_TOO_MANY_FILES,
        (
            f"Candidate file list has {len(paths)} entries; scanning first "
            f"{budget.limits.max_candidate_files} only in sync mode."
        ),
        candidate_files=len(paths),
        scan_cap=budget.limits.max_candidate_files,
    )
    return paths[: budget.limits.max_candidate_files]
