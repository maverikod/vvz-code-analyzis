"""
Full-text search API for database client.

Provides full-text search over code_content_fts (FTS5) with project filter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .client_base import _DatabaseClientBase

# FTS5 MATCH "column:term" only allows these code_content_fts column names; any other
# "word:" is treated as a column filter and can raise "no such column: <name>".
_ALLOWED_FTS5_MATCH_COLUMNS = frozenset(
    {"entity_type", "entity_name", "content", "docstring"}
)

_FTS5_BOGUS_COLUMN_COLON = re.compile(r"(^|\s)([\w.-]+):(\S+)")

# PostgreSQL rejects inputs longer than ~1 MiB for to_tsvector(); UTF-8 can be 4 bytes/char.
_PG_TSVECTOR_INPUT_MAX_CHARS = 200_000


def plain_query_to_fts5_match(query: str) -> Optional[str]:
    """Turn free-text user input into a safe FTS5 MATCH string for code_content_fts.

    - Strips; empty / whitespace-only -> None.
    - Replaces ``/`` with space (path-like queries).
    - Replaces ``unknown:token`` patterns where ``unknown`` is not a real FTS column
      with ``unknown token`` so FTS5 does not interpret a bogus column name.
    """
    s = (query or "").strip()
    if not s:
        return None
    s = s.replace("/", " ")

    def _colon_repl(m: re.Match[str]) -> str:
        """Return colon repl."""
        prefix, col, rest = m.group(1), m.group(2), m.group(3)
        if col.lower() in _ALLOWED_FTS5_MATCH_COLUMNS:
            return m.group(0)
        return f"{prefix}{col} {rest}"

    s = _FTS5_BOGUS_COLUMN_COLON.sub(_colon_repl, s)
    # Hyphens between word chars: FTS5 can mis-parse tokens (e.g. "mcp-proxy-adapter"
    # may raise "no such column: proxy"). Plain-text search: split hyphenated words.
    s = re.sub(r"(?<=[\w])-(?=[\w])", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    return s


class _ClientAPISearchMixin(_DatabaseClientBase):
    """Mixin with full-text search over code content (FTS5)."""

    def _use_postgresql_fulltext_sql(self) -> bool:
        """Use PostgreSQL ``tsvector`` / ``plainto_tsquery`` when driver is ``postgres``.

        Backend is taken from :attr:`DatabaseClient._driver_type` (set from
        ``code_analysis.database.driver.type`` in the config factory), not from DB probing.
        """
        return getattr(self, "_driver_type", None) == "postgres"

    def _full_text_search_postgresql(
        self,
        fts_query: str,
        project_id: str,
        entity_type: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """PostgreSQL: ``tsvector`` / ``plainto_tsquery`` over ``code_content`` rows."""
        cap = _PG_TSVECTOR_INPUT_MAX_CHARS
        # Use the ``simple`` text search config so identifiers (classes, methods,
        # variables) are not stemmed away like common English words.
        sql = f"""
            SELECT
                c.entity_type,
                c.entity_name,
                c.content,
                c.docstring,
                f.path AS file_path,
                ts_rank_cd(
                    to_tsvector(
                        'simple',
                        left(
                            coalesce(c.content, '') || ' ' || coalesce(c.docstring, '')
                            || ' ' || coalesce(c.entity_name, ''),
                            {cap}
                        )
                    ),
                    plainto_tsquery('simple', ?)
                ) AS bm25_score
            FROM code_content c
            INNER JOIN files f ON f.id = c.file_id
            WHERE f.project_id = ?
              AND to_tsvector(
                    'simple',
                    left(
                        coalesce(c.content, '') || ' ' || coalesce(c.docstring, '')
                        || ' ' || coalesce(c.entity_name, ''),
                        {cap}
                    )
                )
                @@ plainto_tsquery('simple', ?)
        """
        params: List[Any] = [fts_query, project_id, fts_query]
        if entity_type:
            sql += " AND c.entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY bm25_score DESC LIMIT ?"
        params.append(limit)

        result = self.execute(sql, tuple(params))
        rows = result.get("data", [])
        if not isinstance(rows, list):
            return []
        return [dict(r) for r in rows]

    def full_text_search(
        self,
        query: str,
        project_id: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Run full-text search in code content, docstrings, and symbol-augmented text.

        Uses SQLite FTS5 table code_content_fts. Joins with code_content and files
        to filter by project_id. Returns entity_type, entity_name, content,
        docstring, and file_path.

        On PostgreSQL, uses ``to_tsvector('simple', ...)`` / ``plainto_tsquery('simple', ...)``
        on ``code_content`` (no FTS5 virtual table; ``simple`` preserves identifiers).

        Args:
            query: FTS5 search query (e.g. word, phrase in double quotes).
            project_id: Project UUID to restrict results.
            entity_type: Optional filter: 'file', 'class', 'function', 'method',
                'variable', 'attribute'.
            limit: Maximum number of results (default 20).

        Returns:
            List of dicts with keys: entity_type, entity_name, content,
            docstring, file_path.

        Raises:
            RPCClientError: If RPC call fails.
            RPCResponseError: If response contains error.
        """
        fts_query = plain_query_to_fts5_match(query)
        if fts_query is None:
            return []

        if self._use_postgresql_fulltext_sql():
            return self._full_text_search_postgresql(
                fts_query, project_id, entity_type, limit
            )

        # FTS5 bm25() returns negative score (less negative = more relevant). Order ASC for best first.
        sql = """
            SELECT
                fts.entity_type,
                fts.entity_name,
                fts.content,
                fts.docstring,
                f.path AS file_path,
                bm25(code_content_fts) AS bm25_score
            FROM code_content_fts fts
            JOIN code_content c ON c.rowid = fts.rowid
            JOIN files f ON f.id = c.file_id
            WHERE f.project_id = ? AND code_content_fts MATCH ?
        """
        params: List[Any] = [project_id, fts_query]
        if entity_type:
            sql += " AND fts.entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY bm25(code_content_fts) ASC LIMIT ?"
        params.append(limit)

        result = self.execute(sql, tuple(params))
        rows = result.get("data", [])
        if not isinstance(rows, list):
            return []
        return [dict(r) for r in rows]
