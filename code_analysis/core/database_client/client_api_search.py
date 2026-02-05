"""
Full-text search API for database client.

Provides full-text search over code_content_fts (FTS5) with project filter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class _ClientAPISearchMixin:
    """Mixin with full-text search over code content (FTS5)."""

    def full_text_search(
        self,
        query: str,
        project_id: str,
        entity_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Run full-text search in code content and docstrings.

        Uses SQLite FTS5 table code_content_fts. Joins with code_content and files
        to filter by project_id. Returns entity_type, entity_name, content,
        docstring, and file_path.

        Args:
            query: FTS5 search query (e.g. word, phrase in double quotes).
            project_id: Project UUID to restrict results.
            entity_type: Optional filter: 'class', 'function', 'method', 'file'.
            limit: Maximum number of results (default 20).

        Returns:
            List of dicts with keys: entity_type, entity_name, content,
            docstring, file_path.

        Raises:
            RPCClientError: If RPC call fails.
            RPCResponseError: If response contains error.
        """
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
            JOIN code_content c ON c.id = fts.rowid
            JOIN files f ON f.id = c.file_id
            WHERE f.project_id = ? AND code_content_fts MATCH ?
        """
        params: List[Any] = [project_id, query]
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
