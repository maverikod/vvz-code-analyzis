"""
Paginated DB queries for list_code_entities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Optional

# Entity-listing predicate (kept as a per-alias template so callers are unchanged).
# Historically this required a populated ``cst_node_id``, but that column is NULL
# for every indexed entity across all projects (the indexer never populates it),
# so the requirement made ``list_code_entities`` return empty everywhere. Relaxed
# to a tautology: entities are listed regardless; ``cst_node_id`` is still selected
# in the output (null when absent), so CST-editing consumers still receive it once
# the indexer populates it. See TZ-CA-INDEX-INTEGRITY-001.
_CST_WHERE = "1=1"


def _file_filter_sql(column: str, file_id: Optional[Any]) -> tuple[str, List[Any]]:
    if file_id is None:
        return "", []
    return f" AND {column} = ?", [file_id]


def count_code_entities(
    db: Any,
    *,
    project_id: str,
    entity_type: Optional[str],
    file_id: Optional[Any],
) -> int:
    """Return total entity rows matching filters."""
    if entity_type == "class":
        return _count_table(
            db,
            f"""
            SELECT COUNT(*) AS cnt FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='c')}
            """,
            _file_filter_sql("c.file_id", file_id),
            [project_id],
        )
    if entity_type == "function":
        return _count_table(
            db,
            f"""
            SELECT COUNT(*) AS cnt FROM functions func
            JOIN files f ON func.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='func')}
            """,
            _file_filter_sql("func.file_id", file_id),
            [project_id],
        )
    if entity_type == "method":
        extra, extra_params = _file_filter_sql("c.file_id", file_id)
        return _count_table(
            db,
            f"""
            SELECT COUNT(*) AS cnt FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='m')}
            {extra}
            """,
            ("", []),
            [project_id, *extra_params],
        )

    # All entity kinds combined.
    parts: List[str] = []
    params: List[Any] = []
    ff, ff_params = _file_filter_sql("c.file_id", file_id)
    parts.append(f"""
        SELECT c.id FROM classes c
        JOIN files f ON c.file_id = f.id
        WHERE f.project_id = ? AND {_CST_WHERE.format(alias='c')}{ff}
        """)
    params.extend([project_id, *ff_params])
    ff, ff_params = _file_filter_sql("func.file_id", file_id)
    parts.append(f"""
        SELECT func.id FROM functions func
        JOIN files f ON func.file_id = f.id
        WHERE f.project_id = ? AND {_CST_WHERE.format(alias='func')}{ff}
        """)
    params.extend([project_id, *ff_params])
    ff, ff_params = _file_filter_sql("c.file_id", file_id)
    parts.append(f"""
        SELECT m.id FROM methods m
        JOIN classes c ON m.class_id = c.id
        JOIN files f ON c.file_id = f.id
        WHERE f.project_id = ? AND {_CST_WHERE.format(alias='m')}{ff}
        """)
    params.extend([project_id, *ff_params])
    sql = "SELECT COUNT(*) AS cnt FROM (" + " UNION ALL ".join(parts) + ") AS combined"
    result = db.execute(sql, tuple(params))
    rows = result.get("data") or []
    if not rows:
        return 0
    return int(rows[0].get("cnt") or 0)


def fetch_code_entities_page(
    db: Any,
    *,
    project_id: str,
    entity_type: Optional[str],
    file_id: Optional[Any],
    limit: int,
    offset: int,
) -> List[dict[str, Any]]:
    """Fetch one page of entities ordered by file_path, line."""
    if entity_type == "class":
        return _fetch_typed(
            db,
            entity_kind="class",
            sql=f"""
            SELECT c.*, f.path AS file_path FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='c')}
            """,
            file_column="c.file_id",
            file_id=file_id,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
    if entity_type == "function":
        return _fetch_typed(
            db,
            entity_kind="function",
            sql=f"""
            SELECT func.*, f.path AS file_path FROM functions func
            JOIN files f ON func.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='func')}
            """,
            file_column="func.file_id",
            file_id=file_id,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
    if entity_type == "method":
        extra, extra_params = _file_filter_sql("c.file_id", file_id)
        sql = f"""
            SELECT m.*, c.name AS class_name, f.path AS file_path FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='m')}
            {extra}
            ORDER BY f.path, m.line
            LIMIT ? OFFSET ?
        """
        params: List[Any] = [project_id, *extra_params, limit, offset]
        return _rows_to_entities(db, "method", sql, params)

    ff_c, ff_c_params = _file_filter_sql("c.file_id", file_id)
    ff_f, ff_f_params = _file_filter_sql("func.file_id", file_id)
    ff_m, ff_m_params = _file_filter_sql("c.file_id", file_id)
    sql = f"""
        SELECT * FROM (
            SELECT 'class' AS type, c.id, c.file_id, c.name, c.line, c.bases,
                   c.docstring, c.cst_node_id, f.path AS file_path,
                   NULL AS class_name
            FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='c')}{ff_c}
            UNION ALL
            SELECT 'function', func.id, func.file_id, func.name, func.line,
                   func.args, func.docstring, func.cst_node_id,
                   f.path, NULL
            FROM functions func
            JOIN files f ON func.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='func')}{ff_f}
            UNION ALL
            SELECT 'method', m.id, c.file_id, m.name, m.line, m.args,
                   m.docstring, m.cst_node_id, f.path, c.name
            FROM methods m
            JOIN classes c ON m.class_id = c.id
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND {_CST_WHERE.format(alias='m')}{ff_m}
        ) AS combined
        ORDER BY file_path, line
        LIMIT ? OFFSET ?
    """
    params = [
        project_id,
        *ff_c_params,
        project_id,
        *ff_f_params,
        project_id,
        *ff_m_params,
        limit,
        offset,
    ]
    result = db.execute(sql, tuple(params))
    rows = result.get("data") or []
    entities: List[dict[str, Any]] = []
    for row in rows:
        if not row.get("file_path"):
            continue
        entities.append(dict(row))
    return entities


def _count_table(
    db: Any,
    sql: str,
    file_filter: tuple[str, List[Any]],
    base_params: List[Any],
) -> int:
    extra_sql, extra_params = file_filter
    full_sql = sql.strip() + extra_sql
    params = [*base_params, *extra_params]
    result = db.execute(full_sql, tuple(params))
    rows = result.get("data") or []
    if not rows:
        return 0
    return int(rows[0].get("cnt") or 0)


def _fetch_typed(
    db: Any,
    *,
    entity_kind: str,
    sql: str,
    file_column: str,
    file_id: Optional[Any],
    project_id: str,
    limit: int,
    offset: int,
) -> List[dict[str, Any]]:
    extra, extra_params = _file_filter_sql(file_column, file_id)
    full_sql = sql.strip() + extra + " ORDER BY f.path, line LIMIT ? OFFSET ?"
    params = [project_id, *extra_params, limit, offset]
    return _rows_to_entities(db, entity_kind, full_sql, params)


def _rows_to_entities(
    db: Any,
    entity_kind: str,
    sql: str,
    params: List[Any],
) -> List[dict[str, Any]]:
    result = db.execute(sql, tuple(params))
    rows = result.get("data") or []
    entities: List[dict[str, Any]] = []
    for row in rows:
        if not row.get("file_path"):
            continue
        entities.append({"type": entity_kind, **row})
    return entities
