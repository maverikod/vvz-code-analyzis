"""
Watch-directory queries scoped to the current server instance.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from code_analysis.core.server_instance import get_server_instance_id


def current_server_instance_id(*, config: Optional[Any] = None) -> str:
    """Return ``registration.instance_uuid`` for this running server."""
    return get_server_instance_id(config=config)


def sql_server_instance_filter(
    column: str = "server_instance_id",
    *,
    config: Optional[Any] = None,
) -> Tuple[str, Tuple[str, ...]]:
    """Return SQL fragment ``col = ?`` and bind params for the current instance."""
    return f"{column} = ?", (current_server_instance_id(config=config),)


def current_server_instance_params(*, config: Optional[Any] = None) -> Tuple[str, ...]:
    """Bind params tuple ``(server_instance_id,)`` for the current instance."""
    return (current_server_instance_id(config=config),)


def sql_projects_server_instance_filter(
    alias: str = "p",
    *,
    config: Optional[Any] = None,
) -> Tuple[str, Tuple[str, ...]]:
    """Return ``alias.server_instance_id = ?`` and bind params."""
    return f"{alias}.server_instance_id = ?", current_server_instance_params(
        config=config
    )


def sql_watch_dir_paths_join(
    projects_alias: str = "p",
    paths_alias: str = "w",
) -> str:
    """JOIN ``watch_dir_paths`` scoped to the same server instance as projects."""
    return (
        f"LEFT JOIN watch_dir_paths {paths_alias} "
        f"ON {paths_alias}.server_instance_id = {projects_alias}.server_instance_id "
        f"AND {paths_alias}.watch_dir_id = {projects_alias}.watch_dir_id"
    )


def _rows_from_execute(
    database: Any, sql: str, params: Optional[tuple] = None
) -> List[dict]:
    """Run SELECT via ``DatabaseClient.execute`` and return row dicts."""
    result = database.execute(sql, params)
    data = result.get("data") if isinstance(result, dict) else None
    return list(data) if isinstance(data, list) else []


def _primary_key_columns(database: Any, table_name: str) -> Tuple[str, ...]:
    """Return primary-key column names for ``table_name`` (PostgreSQL)."""
    rows = _rows_from_execute(
        database,
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = current_schema()
          AND tc.table_name = ?
        ORDER BY kcu.ordinal_position
        """,
        (table_name,),
    )
    return tuple(str(r["column_name"]) for r in rows)


def watch_dirs_upsert_conflict_target(database: Any) -> str:
    """``ON CONFLICT`` target for ``watch_dirs`` upserts (composite or legacy ``id``)."""
    pk_cols = _primary_key_columns(database, "watch_dirs")
    if pk_cols == ("server_instance_id", "id"):
        return "(server_instance_id, id)"
    return "(id)"


def watch_dir_paths_upsert_conflict_target(database: Any) -> str:
    """``ON CONFLICT`` target for ``watch_dir_paths`` upserts."""
    pk_cols = _primary_key_columns(database, "watch_dir_paths")
    if pk_cols == ("server_instance_id", "watch_dir_id"):
        return "(server_instance_id, watch_dir_id)"
    return "(watch_dir_id)"
