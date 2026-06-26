"""
Core merge, scoring, and path normalization for project_cross_search.

Pure helpers testable without live database or filesystem.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Set, Tuple

SourceType = Literal[
    "semantic",
    "fulltext",
    "grep",
    "fulltext_index",
    "grep_unindexed",
    "grep_changed",
    "grep_draft",
]
Confidence = Literal["high", "medium", "low"]
Mode = Literal[
    "union",
    "intersection",
    "strict",
    "semantic_first",
    "grep_first",
    "fulltext_first",
]
Profile = Literal["generic", "command_audit"]

MODES: Tuple[Mode, ...] = (
    "union",
    "intersection",
    "strict",
    "semantic_first",
    "grep_first",
    "fulltext_first",
)
PROFILES: Tuple[Profile, ...] = ("generic", "command_audit")

GREP_LINE_ONLY_IGNORED = "GREP_LINE_ONLY_IGNORED"

STRUCTURAL_GREP_SOURCES: frozenset[str] = frozenset(
    {"grep_unindexed", "grep_changed", "grep_draft"}
)

COMMAND_AUDIT_GREP_PATTERNS: Tuple[str, ...] = (
    "get_schema",
    "execute",
    "session_id",
    "touch_or_error",
    "SessionNotFoundError",
    "SESSION_NOT_FOUND",
    "enforce_security_policy",
    "COMMAND_FORBIDDEN",
    "register_auto_import_module",
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "had",
        "her",
        "was",
        "one",
        "our",
        "out",
        "day",
        "get",
        "has",
        "him",
        "his",
        "how",
        "its",
        "may",
        "new",
        "now",
        "old",
        "see",
        "two",
        "way",
        "who",
        "did",
        "let",
        "put",
        "say",
        "she",
        "too",
        "use",
        "what",
        "when",
        "where",
        "which",
        "with",
        "that",
        "this",
        "from",
        "have",
        "been",
        "were",
        "will",
        "would",
        "could",
        "should",
        "about",
        "into",
        "than",
        "then",
        "them",
        "they",
        "their",
        "there",
        "these",
        "those",
        "does",
        "done",
        "being",
        "after",
        "before",
        "never",
        "registered",
        "rejects",
        "command",
        "client",
        "when",
        "require",
        "requires",
        "requiring",
        "mcp",
        "commands",
    }
)

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_ERROR_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9_]{3,}")
_DOTTED_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")

_CONFIDENCE_BASE = {"high": 3000, "medium": 2000, "low": 1000}

_EXCEPTION_ALWAYS_ALLOWED = frozenset({"session_create"})
_EXCEPTION_CONDITIONAL = frozenset({"session_list"})
_EXCEPTION_INFRA_REVIEW = frozenset(
    {
        "help",
        "health",
        "config",
        "settings",
        "queue_get_job_status",
        "queue_get_job_logs",
        "queue_list_jobs",
    }
)


def json_safe_scalar(value: Any) -> Any:
    """Coerce DB/NumPy scalars to JSON-serializable Python types."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return float(value)
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except TypeError, ValueError:
            pass
    try:
        return float(value)
    except TypeError, ValueError:
        return str(value)


def json_safe_line_number(value: Any) -> Optional[int]:
    """Best-effort line number for evidence rows."""
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


@dataclass
class PathFilterOptions:
    """Post-normalization path filters for merged candidates."""

    include_docs: bool = True
    include_tests: bool = True
    include_hidden: bool = False
    include_venv: bool = False
    file_pattern: str = ""


@dataclass
class SearchPlan:
    """Resolved search parameters for one cross-search invocation."""

    semantic_limit: int = 30
    fulltext_limit: int = 30
    grep_limit: int = 200
    grep_patterns: List[str] = field(default_factory=list)
    derived_grep_patterns: List[str] = field(default_factory=list)
    file_pattern: str = ""
    entity_type: Optional[str] = None
    mode: Mode = "intersection"
    profile: Profile = "generic"
    limit: int = 20
    min_semantic_score: float = 0.45
    case_sensitive: bool = False
    literal: bool = True


def derive_grep_patterns_from_query(query: str, *, max_patterns: int = 8) -> List[str]:
    """Derive weak literal grep markers from a natural-language query."""
    tokens: List[str] = []
    seen: Set[str] = set()
    for regex in (_ERROR_TOKEN_RE, _DOTTED_RE, _IDENTIFIER_RE):
        for match in regex.finditer(query):
            token = match.group(0)
            key = token.lower()
            if len(token) < 3:
                continue
            if key in _STOPWORDS:
                continue
            if key in seen:
                continue
            seen.add(key)
            tokens.append(token)
            if len(tokens) >= max_patterns:
                return tokens
    return tokens


def build_grep_pattern_list(
    query: str,
    explicit_patterns: Sequence[str],
    profile: Profile,
) -> Tuple[List[str], List[str]]:
    """Return (final_patterns, derived_patterns)."""
    derived: List[str] = []
    patterns: List[str] = []
    seen: Set[str] = set()

    def _add(p: str) -> None:
        """Append a non-empty pattern once, case-insensitively."""
        p = (p or "").strip()
        if not p:
            return
        key = p.lower()
        if key in seen:
            return
        seen.add(key)
        patterns.append(p)

    for p in explicit_patterns:
        _add(p)

    if not explicit_patterns:
        derived = derive_grep_patterns_from_query(query)
        for p in derived:
            _add(p)

    if profile == "command_audit":
        for p in COMMAND_AUDIT_GREP_PATTERNS:
            _add(p)

    return patterns, derived


def normalize_file_path(
    file_path: str,
    project_root: Optional[Path] = None,
) -> str:
    """Convert absolute paths under project_root to stable project-relative posix paths."""
    raw = (file_path or "").strip().replace("\\", "/")
    if not raw:
        return raw
    if project_root is None:
        return raw.lstrip("./")
    path = Path(raw)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()
    return raw.lstrip("./")


def path_passes_filters(
    file_path: str,
    options: PathFilterOptions,
) -> bool:
    """Apply include_docs/tests/hidden/venv and optional file_pattern filters."""
    rel = file_path.replace("\\", "/")
    if not options.include_docs:
        if rel.startswith("docs/") or "/docs/" in rel:
            return False
    if not options.include_tests:
        if (
            rel.startswith("tests/")
            or rel.startswith("test_data/")
            or "/tests/" in rel
            or "/test_data/" in rel
        ):
            return False
    if not options.include_venv:
        parts = rel.split("/")
        if any(p in (".venv", "venv", "site-packages") for p in parts):
            return False
    if not options.include_hidden:
        parts = rel.split("/")
        for part in parts:
            if part.startswith(".") and part != ".github":
                return False
    if options.file_pattern:
        from .file_management.relative_path_list_pattern import (
            relative_path_matches_listing_pattern,
        )

        if not relative_path_matches_listing_pattern(rel, options.file_pattern):
            return False
    return True


def normalize_semantic_hit(
    row: Dict[str, Any], project_root: Optional[Path]
) -> Dict[str, Any]:
    """Normalize a semantic-search row into cross-search evidence."""
    raw_score = row.get("score")
    score = json_safe_scalar(raw_score) if raw_score is not None else None
    line = json_safe_line_number(row.get("line"))
    metadata: Dict[str, Any] = {}
    for key in (
        "distance",
        "chunk_id",
        "chunk_uuid",
        "file_id",
        "vector_id",
        "vector_backend",
        "token_count",
    ):
        if row.get(key) is not None:
            metadata[key] = json_safe_scalar(row.get(key))
    return {
        "source": "semantic",
        "file_path": normalize_file_path(str(row.get("file_path") or ""), project_root),
        "line_start": line,
        "line_end": line,
        "score": score,
        "text": row.get("text") if row.get("text") is not None else None,
        "entity_type": row.get("chunk_type"),
        "entity_name": None,
        "metadata": metadata,
    }


def normalize_fulltext_hit(
    row: Dict[str, Any], project_root: Optional[Path]
) -> Dict[str, Any]:
    """Normalize a full-text row into cross-search evidence."""
    raw_score = row.get("bm25_score")
    if raw_score is None:
        raw_score = row.get("score")
    score = json_safe_scalar(raw_score) if raw_score is not None else None
    return {
        "source": "fulltext",
        "file_path": normalize_file_path(str(row.get("file_path") or ""), project_root),
        "line_start": None,
        "line_end": None,
        "score": score,
        "text": row.get("content"),
        "entity_type": row.get("entity_type"),
        "entity_name": row.get("entity_name"),
        "metadata": {
            "docstring": row["docstring"]
            for _ in (0,)
            if row.get("docstring") is not None
        },
    }


def is_structural_grep_evidence(item: Dict[str, Any]) -> bool:
    """
    True when grep hit is safe to merge as cross-search evidence.

    Line-only grep must not count toward evidence_score or confidence.
    """
    meta = item.get("metadata") or {}
    status = meta.get("enrichment_status") or item.get("enrichment_status")
    if status != "enriched":
        return False
    preview = meta.get("preview") or item.get("preview")
    if not preview:
        return False
    node_ref = meta.get("node_ref") or item.get("node_ref")
    selector = meta.get("selector") or item.get("selector")
    if not node_ref and not selector:
        return False
    source = str(item.get("source") or "")
    return source in STRUCTURAL_GREP_SOURCES


def partition_grep_for_cross_search(
    hits: Sequence[Dict[str, Any]],
    *,
    require_structural: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """
    Split normalized grep hits into structural evidence vs line-only rejects.

    Returns (structural_hits, line_only_hits, line_only_count).
    """
    if not require_structural:
        return list(hits), [], 0
    structural: List[Dict[str, Any]] = []
    line_only: List[Dict[str, Any]] = []
    for hit in hits:
        if is_structural_grep_evidence(hit):
            structural.append(hit)
        else:
            line_only.append(hit)
    return structural, line_only, len(line_only)


def normalize_grep_hit(
    row: Dict[str, Any],
    pattern: str,
    project_root: Optional[Path],
) -> Dict[str, Any]:
    """Normalize a grep row and its pattern into cross-search evidence."""
    rel = row.get("relative_path")
    if rel is None:
        rel = row.get("file_path") or ""
    line = json_safe_line_number(row.get("line_number"))
    metadata: Dict[str, Any] = {"pattern": pattern}
    for key in (
        "block_id",
        "block_type",
        "node_ref",
        "selector",
        "preview",
        "session_id",
        "enrichment_status",
        "start_line",
        "end_line",
        "qualname",
        "grep_source",
    ):
        if row.get(key) is not None:
            metadata[key] = row.get(key)
    raw_source = row.get("source")
    if raw_source in (
        "grep_unindexed",
        "grep_changed",
        "grep_draft",
        "fulltext_index",
    ):
        source_label = str(raw_source)
    else:
        source_label = "grep"
    end_line = json_safe_line_number(row.get("end_line")) or line
    return {
        "source": source_label,
        "file_path": normalize_file_path(str(rel or ""), project_root),
        "line_start": line,
        "line_end": end_line,
        "score": None,
        "text": row.get("line") if row.get("line") is not None else None,
        "entity_type": row.get("block_type"),
        "entity_name": None,
        "metadata": metadata,
        "enrichment_status": metadata.get("enrichment_status"),
    }


def _confidence_label(evidence_score: int) -> Confidence:
    """Map independent evidence count to a confidence label."""
    if evidence_score >= 3:
        return "high"
    if evidence_score == 2:
        return "medium"
    return "low"


def _normalized_fulltext_score(items: Sequence[Dict[str, Any]]) -> float:
    """Convert the best negative BM25 score into a positive rank signal."""
    scores: List[float] = []
    for item in items:
        raw = item.get("score")
        if raw is None:
            continue
        try:
            scores.append(float(raw))
        except TypeError, ValueError:
            continue
    if not scores:
        return 0.0
    # FTS bm25 is negative (closer to 0 is better); invert to a positive rank signal.
    best = max(scores)
    return min(100.0, max(0.0, -best))


def _best_semantic_score(items: Sequence[Dict[str, Any]]) -> float:
    """Return the highest valid semantic score in an evidence group."""
    best = 0.0
    for item in items:
        raw = item.get("score")
        if raw is None:
            continue
        try:
            best = max(best, float(raw))
        except TypeError, ValueError:
            continue
    return best


def merge_evidence(
    semantic: Sequence[Dict[str, Any]],
    fulltext: Sequence[Dict[str, Any]],
    grep: Sequence[Dict[str, Any]],
    *,
    path_filters: PathFilterOptions,
    mode: Mode,
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """Group normalized evidence by file_path, score, filter by mode, and truncate."""
    structural_grep_count = sum(1 for i in grep if is_structural_grep_evidence(i))
    source_counts = {
        "semantic": len(semantic),
        "fulltext": len(fulltext),
        "grep": structural_grep_count,
        "grep_raw": len(grep),
        "grep_structural": structural_grep_count,
        "grep_line_only_ignored": max(0, len(grep) - structural_grep_count),
    }
    grouped: Dict[str, Dict[str, Any]] = {}

    def _ensure(path: str) -> Optional[Dict[str, Any]]:
        """Return or create a filtered evidence bucket for a file path."""
        if not path:
            return None
        if not path_passes_filters(path, path_filters):
            return None
        if path not in grouped:
            grouped[path] = {
                "file_path": path,
                "evidence": {"semantic": [], "fulltext": [], "grep": []},
            }
        return grouped[path]

    for item in semantic:
        bucket = _ensure(str(item.get("file_path") or ""))
        if bucket is not None:
            bucket["evidence"]["semantic"].append(item)
    for item in fulltext:
        bucket = _ensure(str(item.get("file_path") or ""))
        if bucket is not None:
            bucket["evidence"]["fulltext"].append(item)
    for item in grep:
        if not is_structural_grep_evidence(item):
            continue
        bucket = _ensure(str(item.get("file_path") or ""))
        if bucket is not None:
            bucket["evidence"]["grep"].append(item)

    candidates: List[Dict[str, Any]] = []
    for path, bucket in grouped.items():
        ev = bucket["evidence"]
        structural_grep = ev["grep"]
        sources = {
            "semantic": bool(ev["semantic"]),
            "fulltext": bool(ev["fulltext"]),
            "grep": bool(structural_grep),
        }
        evidence_score = sum(1 for v in sources.values() if v)
        confidence = _confidence_label(evidence_score)
        ranking_score = float(_CONFIDENCE_BASE[confidence])
        ranking_score += _best_semantic_score(ev["semantic"]) * 100.0
        ranking_score += _normalized_fulltext_score(ev["fulltext"])
        ranking_score += float(min(len(structural_grep), 20))

        why: List[str] = []
        if sources["semantic"]:
            why.append("semantic index returned related chunks")
        if sources["fulltext"]:
            why.append("full-text index matched identifiers or content")
        if sources["grep"]:
            why.append("filesystem grep found preview-compatible structural blocks")

        candidates.append(
            {
                "file_path": path,
                "confidence": confidence,
                "evidence_score": evidence_score,
                "ranking_score": ranking_score,
                "sources": sources,
                "evidence": ev,
                "why": why,
            }
        )

    all_candidates = list(candidates)
    filtered = apply_mode(candidates, mode)
    _confidence_rank = {"high": 3, "medium": 2, "low": 1}

    def _sort_key(cand: Dict[str, Any]) -> tuple:
        """Sort candidates by confidence, evidence, rank, and path."""
        conf = cand.get("confidence")
        if conf not in _confidence_rank:
            conf = _confidence_label(int(cand.get("evidence_score") or 0))
        return (
            -_confidence_rank.get(conf, 1),
            -int(cand.get("evidence_score") or 0),
            -float(cand.get("ranking_score") or 0),
            str(cand.get("file_path") or ""),
        )

    filtered.sort(key=_sort_key)
    return all_candidates, filtered[:limit], source_counts


def apply_mode(
    candidates: Sequence[Dict[str, Any]], mode: Mode
) -> List[Dict[str, Any]]:
    """Filter and re-rank candidates according to the selected mode."""
    out: List[Dict[str, Any]] = []
    for cand in candidates:
        score = int(cand.get("evidence_score") or 0)
        sources = cand.get("sources") or {}
        include = False
        bonus = 0.0
        if mode == "union":
            include = score >= 1
        elif mode == "intersection":
            include = score >= 2
        elif mode == "strict":
            include = score == 3
        elif mode == "semantic_first":
            include = bool(sources.get("semantic"))
            bonus = 500.0
        elif mode == "grep_first":
            include = bool(sources.get("grep"))
            bonus = 500.0
        elif mode == "fulltext_first":
            include = bool(sources.get("fulltext"))
            bonus = 500.0
        if include:
            row = dict(cand)
            row["ranking_score"] = float(row.get("ranking_score") or 0) + bonus
            out.append(row)
    return out


def _grep_text_blob(grep_items: Sequence[Dict[str, Any]]) -> str:
    """Join grep evidence text for profile-specific inspection."""
    return "\n".join(str(i.get("text") or "") for i in grep_items)


def _infer_command_name(file_path: str) -> Optional[str]:
    """Infer a command name from a Python command module path."""
    name = Path(file_path).name
    if name.endswith("_command.py"):
        return name[: -len("_command.py")]
    if name.endswith(".py") and "commands" in file_path.replace("\\", "/"):
        stem = Path(name).stem
        if stem.endswith("_command"):
            return stem[: -len("_command")]
    return None


def build_command_audit(
    file_path: str,
    grep_evidence: Sequence[Dict[str, Any]],
    *,
    registered_commands: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Build command_audit evidence block for command_audit profile."""
    blob = _grep_text_blob(grep_evidence)
    command_name = _infer_command_name(file_path)
    audit: Dict[str, Any] = {
        "command_name": command_name,
        "file_path": file_path,
        "registered_in_hooks": bool(
            registered_commands and command_name and command_name in registered_commands
        ),
        "has_get_schema": "get_schema" in blob or "def get_schema" in blob,
        "schema_mentions_session_id": "session_id" in blob,
        "execute_accepts_session_id": "session_id" in blob and "execute" in blob,
        "calls_touch_or_error": "touch_or_error" in blob,
        "catches_SessionNotFoundError": "SessionNotFoundError" in blob,
        "returns_SESSION_NOT_FOUND": "SESSION_NOT_FOUND" in blob,
        "calls_enforce_security_policy": "enforce_security_policy" in blob,
        "is_exception_candidate": command_name in _EXCEPTION_ALWAYS_ALLOWED
        or command_name in _EXCEPTION_CONDITIONAL
        or command_name in _EXCEPTION_INFRA_REVIEW,
        "needs_session_guard": False,
    }
    if command_name in _EXCEPTION_ALWAYS_ALLOWED:
        audit["exception_category"] = "always_allowed_without_session"
    elif command_name in _EXCEPTION_CONDITIONAL:
        audit["exception_category"] = "conditionally_allowed_without_session"
    elif command_name in _EXCEPTION_INFRA_REVIEW:
        audit["exception_category"] = "server_infrastructure_review_required"
    else:
        audit["exception_category"] = None
        if "code_analysis/commands" in file_path.replace("\\", "/"):
            missing_guard = not (
                audit["schema_mentions_session_id"]
                and audit["calls_touch_or_error"]
                and audit["returns_SESSION_NOT_FOUND"]
            )
            audit["needs_session_guard"] = missing_guard
    return audit


def build_summary(
    all_candidates: Sequence[Dict[str, Any]],
    returned: Sequence[Dict[str, Any]],
    source_counts: Dict[str, int],
    *,
    profile: Profile,
    warnings: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate response summary block."""
    summary: Dict[str, Any] = {
        "total_candidates": len(all_candidates),
        "returned": len(returned),
        "high_confidence": sum(1 for c in returned if c.get("confidence") == "high"),
        "medium_confidence": sum(
            1 for c in returned if c.get("confidence") == "medium"
        ),
        "low_confidence": sum(1 for c in returned if c.get("confidence") == "low"),
        "source_counts": source_counts,
        "filtered_out": {
            "by_mode": max(0, len(all_candidates) - len(returned)),
        },
        "warnings": list(warnings),
    }
    if profile == "command_audit":
        summary["command_audit_summary"] = {
            "candidates": len(all_candidates),
            "needs_session_guard": sum(
                1
                for c in returned
                if (c.get("command_audit") or {}).get("needs_session_guard")
            ),
            "exception_candidates": sum(
                1
                for c in returned
                if (c.get("command_audit") or {}).get("is_exception_candidate")
            ),
        }
    return summary
