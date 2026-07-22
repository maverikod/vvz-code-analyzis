"""
Fulltext index coverage checks for grep index-gap fallback.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Literal, Optional

from code_analysis.core.database_driver_pkg.domain.files import get_file_by_path
from code_analysis.core.structure_extraction.format_registry import (
    is_supported_extension,
)

CoverageReason = Literal[
    "indexed_current",
    "not_indexed",
    "changed_since_index",
    "missing_content",
    "unsupported_format",
    "deleted",
]


@dataclass
class IndexedCoverage:
    """Represent IndexedCoverage."""

    file_path: str
    indexed: bool
    unchanged: bool
    reason: CoverageReason

    def as_dict(self) -> dict[str, Any]:
        """Return as dict."""
        return {
            "file_path": self.file_path,
            "indexed": self.indexed,
            "unchanged": self.unchanged,
            "reason": self.reason,
        }


class IndexCoverageService:
    """Determine which project files are covered by the fulltext index."""

    def __init__(self, database: Any, project_id: str, project_root: Path) -> None:
        """Initialize the instance."""
        self._db = database
        self._project_id = project_id
        self._root = project_root.resolve()

    def check_path(self, rel_path: str) -> IndexedCoverage:
        """Return check path."""
        rel = rel_path.replace("\\", "/").lstrip("/")
        if not is_supported_extension(rel):
            return IndexedCoverage(
                file_path=rel,
                indexed=False,
                unchanged=False,
                reason="unsupported_format",
            )
        abs_path = (self._root / rel).resolve()
        row = get_file_by_path(self._db, str(abs_path), self._project_id)
        if row is None:
            return IndexedCoverage(
                file_path=rel,
                indexed=False,
                unchanged=False,
                reason="not_indexed",
            )
        if row.get("deleted"):
            return IndexedCoverage(
                file_path=rel,
                indexed=False,
                unchanged=False,
                reason="deleted",
            )
        file_id = row.get("id")
        if file_id is None:
            return IndexedCoverage(
                file_path=rel,
                indexed=False,
                unchanged=False,
                reason="not_indexed",
            )
        content_count = self._count_code_content(file_id)
        if content_count == 0:
            return IndexedCoverage(
                file_path=rel,
                indexed=False,
                unchanged=False,
                reason="missing_content",
            )
        if not abs_path.is_file():
            return IndexedCoverage(
                file_path=rel,
                indexed=True,
                unchanged=False,
                reason="changed_since_index",
            )
        disk_mtime = abs_path.stat().st_mtime
        db_mtime = float(row.get("last_modified") or 0.0)
        if disk_mtime > db_mtime + 1e-6:
            return IndexedCoverage(
                file_path=rel,
                indexed=True,
                unchanged=False,
                reason="changed_since_index",
            )
        try:
            disk_text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return IndexedCoverage(
                file_path=rel,
                indexed=True,
                unchanged=False,
                reason="changed_since_index",
            )
        disk_hash = hashlib.sha256(disk_text.encode("utf-8")).hexdigest()
        indexed_hash = self._latest_cst_hash(file_id)
        if indexed_hash and indexed_hash == disk_hash:
            return IndexedCoverage(
                file_path=rel,
                indexed=True,
                unchanged=True,
                reason="indexed_current",
            )
        if db_mtime >= disk_mtime - 1e-6:
            return IndexedCoverage(
                file_path=rel,
                indexed=True,
                unchanged=True,
                reason="indexed_current",
            )
        return IndexedCoverage(
            file_path=rel,
            indexed=True,
            unchanged=False,
            reason="changed_since_index",
        )

    def filter_grep_candidates(
        self,
        rel_paths: List[str],
        *,
        skip_indexed_unchanged: bool,
        indexed_only: bool,
    ) -> List[str]:
        """Return paths that should be scanned by grep fallback."""
        kept, _ = self.filter_grep_candidates_with_reasons(
            rel_paths,
            skip_indexed_unchanged=skip_indexed_unchanged,
            indexed_only=indexed_only,
        )
        return kept

    def filter_grep_candidates_with_reasons(
        self,
        rel_paths: List[str],
        *,
        skip_indexed_unchanged: bool,
        indexed_only: bool,
    ) -> tuple[List[str], dict[str, IndexedCoverage]]:
        """Return kept paths and per-path coverage for grep source labeling."""
        out: List[str] = []
        reasons: dict[str, IndexedCoverage] = {}
        for rel in rel_paths:
            cov = self.check_path(rel)
            reasons[rel] = cov
            if indexed_only:
                if cov.indexed and not cov.unchanged:
                    out.append(rel)
                continue
            if skip_indexed_unchanged and cov.indexed and cov.unchanged:
                continue
            if cov.reason == "deleted":
                continue
            out.append(rel)
        return out, reasons

    def _count_code_content(self, file_id: Any) -> int:
        """Return count code content."""
        result = self._db.execute(
            "SELECT COUNT(*) AS c FROM code_content WHERE file_id = ?",
            (file_id,),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        if not rows:
            return 0
        return int(rows[0].get("c") or 0)

    def _latest_cst_hash(self, file_id: Any) -> Optional[str]:
        """Return latest cst hash."""
        result = self._db.execute(
            "SELECT cst_hash FROM cst_trees WHERE file_id = ? ORDER BY file_mtime DESC LIMIT 1",
            (file_id,),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        if not rows:
            return None
        raw = rows[0].get("cst_hash")
        return str(raw) if raw else None
