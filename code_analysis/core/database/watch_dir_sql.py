"""
Portable watch_dirs / watch_dir_paths upsert SQL (SQLite ``INSERT OR REPLACE``).

PostgreSQL translation lives in
:mod:`code_analysis.core.database_driver_pkg.drivers.postgres_run`
(norm lookup must stay aligned with these statements).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from code_analysis.core.sql_portable import sql_julian_timestamp_now_expr


def watch_dirs_insert_new_row_sql() -> str:
    """Plain INSERT for a new watch_dir row (mount sync); ``deleted`` is a bind param."""
    return (
        "INSERT INTO watch_dirs (server_instance_id, id, name, deleted, updated_at) "
        "VALUES (?, ?, ?, ?, julianday('now'))"
    )


def watch_dirs_insert_or_replace_sql(database: Any) -> str:
    """``INSERT OR REPLACE`` for ``watch_dirs`` (partitioned by ``server_instance_id``)."""
    _now = sql_julian_timestamp_now_expr(database)
    return (
        "INSERT OR REPLACE INTO watch_dirs "
        f"(server_instance_id, id, name, deleted, updated_at) "
        f"VALUES (?, ?, ?, ?, {_now})"
    )


def watch_dir_paths_insert_or_replace_sql(database: Any) -> str:
    """``INSERT OR REPLACE`` for ``watch_dir_paths`` with absolute path."""
    _now = sql_julian_timestamp_now_expr(database)
    return (
        "INSERT OR REPLACE INTO watch_dir_paths "
        f"(server_instance_id, watch_dir_id, absolute_path, updated_at) "
        f"VALUES (?, ?, ?, {_now})"
    )


def watch_dir_paths_insert_or_replace_null_sql(database: Any) -> str:
    """``INSERT OR REPLACE`` for ``watch_dir_paths`` with ``NULL`` absolute path."""
    _now = sql_julian_timestamp_now_expr(database)
    return (
        "INSERT OR REPLACE INTO watch_dir_paths "
        f"(server_instance_id, watch_dir_id, absolute_path, updated_at) "
        f"VALUES (?, ?, NULL, {_now})"
    )


def watch_dirs_upsert_norm_for_postgres_adapter() -> str:
    """Normalized SQL (post-julianday rewrite) for ``postgres_run`` lookup."""
    return (
        "INSERT OR REPLACE INTO watch_dirs "
        "(server_instance_id, id, name, deleted, updated_at) "
        "VALUES (?, ?, ?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
    )


def watch_dir_paths_upsert_norm_for_postgres_adapter() -> str:
    return (
        "INSERT OR REPLACE INTO watch_dir_paths "
        "(server_instance_id, watch_dir_id, absolute_path, updated_at) "
        "VALUES (?, ?, ?, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
    )


def watch_dir_paths_upsert_null_norm_for_postgres_adapter() -> str:
    return (
        "INSERT OR REPLACE INTO watch_dir_paths "
        "(server_instance_id, watch_dir_id, absolute_path, updated_at) "
        "VALUES (?, ?, NULL, (EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)))"
    )
