"""
Grep-evidence normalization helpers used by ``search_paginated_cross``.

Extracted verbatim from the deleted ``project_cross_search_core.py`` (dead
cross-search command removal, bug — cross-search redundant with
``search(project_id=None)``): these were the ONLY two of that module's ~20
helpers with a live importer (``search_paginated_cross.py``); everything else
in the old module was reachable only through the deleted
``project_cross_search_command.py`` chain. Kept as a small standalone module
(not folded directly into ``search_paginated_cross.py``) since both symbols
are pure, independently unit-tested helpers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

STRUCTURAL_GREP_SOURCES: frozenset[str] = frozenset(
    {"grep_unindexed", "grep_changed", "grep_draft"}
)


def json_safe_line_number(value: Any) -> Optional[int]:
    """Best-effort line number for evidence rows."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def normalize_grep_hit(
    row: Dict[str, Any],
    pattern: str,
    project_root: Optional[Path],
) -> Dict[str, Any]:
    """Map a raw grep row to the normalized evidence shape merged into cross findings."""
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
