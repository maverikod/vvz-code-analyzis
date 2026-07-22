"""
Full-text search, ported driver-direct (stage 2 layer collapse, Part 1).

Free-function port of ``code_analysis.core.database_client.client_api_search``'s
``_ClientAPISearchMixin.full_text_search``/``_full_text_search_postgresql``. Takes
``driver: Any`` (duck-typed against ``execute`` - see
scratchpad/stage2-parity-spike.md) instead of ``self``.

``plain_query_to_fts5_match`` was already a module-level free function in
``client_api_search.py`` (not a mixin method) - re-exported here unchanged so
callers of this module do not also need to import from the client package.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analysis.core.database_client.client_api_search import (
    plain_query_to_fts5_match,
)

__all__ = ["plain_query_to_fts5_match", "full_text_search"]

# PostgreSQL rejects inputs longer than ~1 MiB for to_tsvector(); UTF-8 can be 4 bytes/char.
_PG_TSVECTOR_INPUT_MAX_CHARS = 200_000


def _full_text_search_postgresql(
    driver: Any,
    fts_query: str,
    project_id: str,
    entity_type: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    """PostgreSQL: ``tsvector`` / ``plainto_tsquery`` over ``code_content`` rows.

    Exact port of ``_ClientAPISearchMixin._full_text_search_postgresql``.
    """
    cap = _PG_TSVECTOR_INPUT_MAX_CHARS
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

    result = driver.execute(sql, tuple(params))
    rows = result.get("data", [])
    if not isinstance(rows, list):
        return []
    return [dict(r) for r in rows]


def full_text_search(
    driver: Any,
    query: str,
    project_id: str,
    entity_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Run full-text search in code content, docstrings, and symbol-augmented text.

    Exact port of ``_ClientAPISearchMixin.full_text_search``.

    Args:
        driver: Driver-shaped object (``execute`` primitive).
        query: Free-text search query (e.g. word, phrase in double quotes).
        project_id: Project UUID to restrict results.
        entity_type: Optional filter: 'file', 'class', 'function', 'method',
            'variable', 'attribute'.
        limit: Maximum number of results (default 20).

    Returns:
        List of dicts with keys: entity_type, entity_name, content,
        docstring, file_path.
    """
    fts_query = plain_query_to_fts5_match(query)
    if fts_query is None:
        return []

    return _full_text_search_postgresql(driver, fts_query, project_id, entity_type, limit)
