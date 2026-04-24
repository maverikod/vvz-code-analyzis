"""PostgreSQL driver: SQLite DML adaptation for execute_batch."""

from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _adapt_sqlite_bool_int_assignments_for_postgres,
    _adapt_sqlite_dml_for_postgres,
)


def test_adapt_indexing_errors_insert_or_replace_to_upsert() -> None:
    raw = (
        "INSERT OR REPLACE INTO indexing_errors "
        "(project_id, file_path, error_type, error_message, created_at) "
        "VALUES (?, ?, ?, ?, julianday('now'))"
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (project_id, file_path) DO UPDATE SET" in out
    assert "EXCLUDED.error_type" in out
    assert "VALUES (?, ?, ?, ?," in out


def test_adapt_julianday_only() -> None:
    sql = "UPDATE t SET x = julianday('now') WHERE id = ?"
    out = _adapt_sqlite_dml_for_postgres(sql)
    assert "julianday" not in out
    assert "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)" in out


def test_adapt_watch_dirs_insert_or_replace_to_upsert() -> None:
    raw = (
        "INSERT OR REPLACE INTO watch_dirs (id, name, updated_at) "
        "VALUES (?, ?, julianday('now'))"
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (id) DO UPDATE SET" in out
    assert "name = EXCLUDED.name" in out


def test_adapt_watch_dir_paths_insert_or_replace_to_upsert() -> None:
    raw = (
        "INSERT OR REPLACE INTO watch_dir_paths "
        "(watch_dir_id, absolute_path, updated_at) "
        "VALUES (?, ?, julianday('now'))"
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (watch_dir_id) DO UPDATE SET" in out


def test_adapt_bool_int_assignments_for_boolean_columns() -> None:
    sql = (
        "UPDATE files SET deleted = 0, has_docstring = 1, "
        "processing_paused = 0 WHERE id = 1"
    )
    out = _adapt_sqlite_bool_int_assignments_for_postgres(sql)
    assert "deleted = FALSE" in out
    assert "has_docstring = TRUE" in out
    assert "processing_paused = FALSE" in out
    # INTEGER column must stay numeric
    assert "WHERE id = 1" in out


def test_adapt_dml_combined_julianday_and_deleted_assignment() -> None:
    raw = "UPDATE files SET deleted = 0, updated_at = julianday('now') WHERE path = ?"
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "deleted = FALSE" in out
    assert "julianday" not in out


def test_adapt_watch_dir_paths_insert_or_replace_null_path_to_upsert() -> None:
    raw = (
        "INSERT OR REPLACE INTO watch_dir_paths "
        "(watch_dir_id, absolute_path, updated_at) "
        "VALUES (?, NULL, julianday('now'))"
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (watch_dir_id) DO UPDATE SET" in out
    assert "VALUES (?, NULL," in out
