"""
Fulltext index coverage checks for grep index-gap fallback.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from code_analysis.core.database_driver_pkg.domain.files import get_file_by_path
from code_analysis.core.database_driver_pkg.domain.projects import get_project
from code_analysis.core.file_identity import file_row_path_match_values
from code_analysis.core.path_normalization import normalize_path_simple
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE
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
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> tuple[List[str], dict[str, IndexedCoverage]]:
        """Return kept paths and per-path coverage for grep source labeling.

        Classifies all candidates with a handful of multi-row queries
        (:meth:`_batch_check_paths`) instead of ``check_path`` per file - the
        per-file version issued up to 3 sequential DB round-trips per
        candidate, which dominated grep prefilter latency on large candidate
        sets (bug 0c124699).

        ``should_cancel``: optional cooperative-cancel probe (e.g.
        ``FsGrepBudgetState.should_cancel``), polled between the batched
        queries. On a positive signal, unclassified candidates default to
        ``not_indexed`` - conservative (they still get grep-scanned) rather
        than silently dropped.
        """
        reasons = self._batch_check_paths(rel_paths, should_cancel=should_cancel)
        out: List[str] = []
        for rel in rel_paths:
            cov = reasons[rel]
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

    def _batch_check_paths(
        self,
        rel_paths: List[str],
        *,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> dict[str, IndexedCoverage]:
        """Classify many paths with a few multi-row queries.

        Produces exactly the same per-path :class:`IndexedCoverage` verdicts as
        calling :meth:`check_path` once per entry, but replaces N sequential
        single-row lookups with: one project fetch, one batched ``files``
        lookup, and two grouped queries (``code_content`` counts and latest
        ``cst_trees`` hash) keyed by the resolved file ids.
        """
        # First occurrence of each original string decides its classification;
        # duplicates in `rel_paths` reuse the same `result[orig]` dict slot,
        # so no separate back-fill pass is needed for repeats.
        result: Dict[str, IndexedCoverage] = {}
        norm_by_orig: Dict[str, str] = {}
        supported_orig: List[str] = []
        for orig in rel_paths:
            if orig in norm_by_orig:
                continue
            rel = orig.replace("\\", "/").lstrip("/")
            norm_by_orig[orig] = rel
            if not is_supported_extension(rel):
                result[orig] = IndexedCoverage(
                    file_path=rel,
                    indexed=False,
                    unchanged=False,
                    reason="unsupported_format",
                )
                continue
            supported_orig.append(orig)

        if not supported_orig:
            return result

        def _fallback_not_indexed(pending: List[str]) -> None:
            """Cancellation checkpoint: mark still-unclassified paths conservatively."""
            for orig in pending:
                result[orig] = IndexedCoverage(
                    file_path=norm_by_orig[orig],
                    indexed=False,
                    unchanged=False,
                    reason="not_indexed",
                )

        if should_cancel is not None and should_cancel():
            _fallback_not_indexed(supported_orig)
            return result

        unique_rels = sorted({norm_by_orig[orig] for orig in supported_orig})
        rows_by_rel = self._fetch_file_rows(unique_rels)

        if should_cancel is not None and should_cancel():
            _fallback_not_indexed(supported_orig)
            return result

        file_ids: List[Any] = []
        for rel in unique_rels:
            row = rows_by_rel.get(rel)
            if row is not None and row.get("id") is not None and not row.get("deleted"):
                file_ids.append(row["id"])

        content_counts = self._batch_code_content_counts(file_ids)
        latest_hashes = self._batch_latest_cst_hashes(file_ids)

        coverage_by_rel: Dict[str, IndexedCoverage] = {}
        for rel in unique_rels:
            coverage_by_rel[rel] = self._classify_row(
                rel=rel,
                row=rows_by_rel.get(rel),
                abs_path=(self._root / rel).resolve(),
                content_counts=content_counts,
                latest_hashes=latest_hashes,
            )

        for orig in supported_orig:
            result[orig] = coverage_by_rel[norm_by_orig[orig]]
        return result

    def _classify_row(
        self,
        *,
        rel: str,
        row: Optional[Dict[str, Any]],
        abs_path: Path,
        content_counts: Dict[Any, int],
        latest_hashes: Dict[Any, Optional[str]],
    ) -> IndexedCoverage:
        """Apply ``check_path``'s exact classification rules to a pre-fetched row."""
        if row is None:
            return IndexedCoverage(
                file_path=rel, indexed=False, unchanged=False, reason="not_indexed"
            )
        if row.get("deleted"):
            return IndexedCoverage(
                file_path=rel, indexed=False, unchanged=False, reason="deleted"
            )
        file_id = row.get("id")
        if file_id is None:
            return IndexedCoverage(
                file_path=rel, indexed=False, unchanged=False, reason="not_indexed"
            )
        content_count = content_counts.get(file_id, 0)
        if content_count == 0:
            return IndexedCoverage(
                file_path=rel, indexed=False, unchanged=False, reason="missing_content"
            )
        if not abs_path.is_file():
            return IndexedCoverage(
                file_path=rel, indexed=True, unchanged=False, reason="changed_since_index"
            )
        disk_mtime = abs_path.stat().st_mtime
        db_mtime = float(row.get("last_modified") or 0.0)
        if disk_mtime > db_mtime + 1e-6:
            return IndexedCoverage(
                file_path=rel, indexed=True, unchanged=False, reason="changed_since_index"
            )
        try:
            disk_text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return IndexedCoverage(
                file_path=rel, indexed=True, unchanged=False, reason="changed_since_index"
            )
        disk_hash = hashlib.sha256(disk_text.encode("utf-8")).hexdigest()
        indexed_hash = latest_hashes.get(file_id)
        if indexed_hash and indexed_hash == disk_hash:
            return IndexedCoverage(
                file_path=rel, indexed=True, unchanged=True, reason="indexed_current"
            )
        if db_mtime >= disk_mtime - 1e-6:
            return IndexedCoverage(
                file_path=rel, indexed=True, unchanged=True, reason="indexed_current"
            )
        return IndexedCoverage(
            file_path=rel, indexed=True, unchanged=False, reason="changed_since_index"
        )

    def _fetch_file_rows(self, rels: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Resolve many project-relative paths to ``files`` rows in one query.

        Mirrors ``get_file_by_path``'s per-path matching (``relative_path``,
        legacy relative ``path``, or legacy absolute ``path``) but issues a
        single ``project_id``-scoped query covering every candidate instead of
        one query per path.
        """
        rows_by_rel: Dict[str, Optional[Dict[str, Any]]] = {rel: None for rel in rels}
        if not rels:
            return rows_by_rel

        project = get_project(self._db, self._project_id)
        if project is None:
            return rows_by_rel

        rel_match_values: set[str] = set()
        path_match_values: set[str] = set()
        match_mode: Dict[str, tuple[str, ...]] = {}
        for rel in rels:
            abs_norm = normalize_path_simple(str((self._root / rel).resolve()))
            try:
                r1, r2, r3 = file_row_path_match_values(
                    project_root=project.root_path, absolute_path=abs_norm
                )
            except ValueError:
                path_match_values.add(abs_norm)
                match_mode[rel] = (abs_norm,)
                continue
            rel_match_values.add(r1)
            path_match_values.add(r2)
            path_match_values.add(r3)
            match_mode[rel] = (r1, r2, r3)

        where_parts: List[str] = []
        params: List[Any] = [self._project_id]
        if rel_match_values:
            placeholders = ",".join(["?"] * len(rel_match_values))
            where_parts.append(f"relative_path IN ({placeholders})")
            params.extend(sorted(rel_match_values))
        if path_match_values:
            placeholders = ",".join(["?"] * len(path_match_values))
            where_parts.append(f"path IN ({placeholders})")
            params.extend(sorted(path_match_values))
        if not where_parts:
            return rows_by_rel

        sql = (
            "SELECT * FROM files WHERE project_id = ? AND "
            f"({' OR '.join(where_parts)}) AND {WHERE_FILES_ACTIVE}"
        )
        result = self._db.execute(sql, tuple(params))
        rows = result.get("data", []) if isinstance(result, dict) else []

        by_relative_path: Dict[str, Dict[str, Any]] = {}
        by_path: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            rp = row.get("relative_path")
            if rp and rp not in by_relative_path:
                by_relative_path[rp] = row
            p = row.get("path")
            if p and p not in by_path:
                by_path[p] = row

        for rel, values in match_mode.items():
            if len(values) == 1:
                (abs_only,) = values
                rows_by_rel[rel] = by_path.get(abs_only)
                continue
            r1, r2, r3 = values
            rows_by_rel[rel] = (
                by_relative_path.get(r1) or by_path.get(r2) or by_path.get(r3)
            )
        return rows_by_rel

    def _batch_code_content_counts(self, file_ids: List[Any]) -> Dict[Any, int]:
        """Return ``file_id -> code_content row count`` for many files in one query."""
        if not file_ids:
            return {}
        unique_ids = sorted(set(file_ids), key=str)
        placeholders = ",".join(["?"] * len(unique_ids))
        result = self._db.execute(
            "SELECT file_id, COUNT(*) AS c FROM code_content "
            f"WHERE file_id IN ({placeholders}) GROUP BY file_id",
            tuple(unique_ids),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        return {row.get("file_id"): int(row.get("c") or 0) for row in rows}

    def _batch_latest_cst_hashes(self, file_ids: List[Any]) -> Dict[Any, Optional[str]]:
        """Return ``file_id -> latest cst_hash`` (by ``file_mtime``) for many files in one query."""
        if not file_ids:
            return {}
        unique_ids = sorted(set(file_ids), key=str)
        placeholders = ",".join(["?"] * len(unique_ids))
        result = self._db.execute(
            "SELECT file_id, cst_hash FROM ("
            "SELECT file_id, cst_hash, "
            "ROW_NUMBER() OVER (PARTITION BY file_id ORDER BY file_mtime DESC) AS rn "
            f"FROM cst_trees WHERE file_id IN ({placeholders})"
            ") ranked WHERE rn = 1",
            tuple(unique_ids),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        out: Dict[Any, Optional[str]] = {}
        for row in rows:
            raw = row.get("cst_hash")
            out[row.get("file_id")] = str(raw) if raw else None
        return out

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
