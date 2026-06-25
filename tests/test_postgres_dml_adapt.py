"""PostgreSQL driver: SQLite DML adaptation for execute_batch."""

import pytest

from code_analysis.core.database_driver_pkg.drivers.postgres_run import (
    _adapt_sqlite_bool_int_assignments_for_postgres,
    _adapt_sqlite_dml_for_postgres,
)
from code_analysis.core.database.code_chunk_sql import (
    CODE_CHUNK_UPSERT_SQL,
    code_chunk_upsert_norm_for_postgres_adapter,
)
from code_analysis.core.vectorization_worker_pkg import batch_processor


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
    from code_analysis.core.database.watch_dir_sql import (
        watch_dirs_upsert_norm_for_postgres_adapter,
    )

    raw = watch_dirs_upsert_norm_for_postgres_adapter().replace(
        "(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))",
        "julianday('now')",
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (server_instance_id, id) DO UPDATE SET" in out
    assert "name = EXCLUDED.name" in out
    assert "deleted = EXCLUDED.deleted" in out


def test_adapt_watch_dir_paths_insert_or_replace_to_upsert() -> None:
    from code_analysis.core.database.watch_dir_sql import (
        watch_dir_paths_upsert_norm_for_postgres_adapter,
    )

    raw = watch_dir_paths_upsert_norm_for_postgres_adapter().replace(
        "(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))",
        "julianday('now')",
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (server_instance_id, watch_dir_id) DO UPDATE SET" in out


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


def test_adapt_watch_dirs_insert_values_deleted_literal() -> None:
    raw = (
        "INSERT INTO watch_dirs (server_instance_id, id, name, deleted, updated_at) "
        "VALUES (?, ?, ?, 0, julianday('now'))"
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "VALUES (?, ?, ?, FALSE," in out
    assert "julianday" not in out


def test_adapt_watch_dirs_insert_bind_param_unchanged() -> None:
    raw = (
        "INSERT INTO watch_dirs (server_instance_id, id, name, deleted, updated_at) "
        "VALUES (?, ?, ?, ?, julianday('now'))"
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "VALUES (?, ?, ?, ?," in out
    assert "FALSE" not in out


def test_adapt_watch_dir_paths_insert_or_replace_null_path_to_upsert() -> None:
    from code_analysis.core.database.watch_dir_sql import (
        watch_dir_paths_upsert_null_norm_for_postgres_adapter,
    )

    raw = watch_dir_paths_upsert_null_norm_for_postgres_adapter().replace(
        "(EXTRACT(JULIAN FROM CURRENT_TIMESTAMP))",
        "julianday('now')",
    )
    out = _adapt_sqlite_dml_for_postgres(raw)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (server_instance_id, watch_dir_id) DO UPDATE SET" in out
    assert "VALUES (?, ?, NULL," in out


def test_adapt_code_chunks_insert_or_replace_to_upsert() -> None:
    """Portable ``code_chunks`` upsert SQL must become valid PostgreSQL upsert."""
    out = _adapt_sqlite_dml_for_postgres(CODE_CHUNK_UPSERT_SQL)
    assert "INSERT OR REPLACE" not in out
    assert "ON CONFLICT (chunk_uuid) DO UPDATE SET" in out
    assert "file_id = EXCLUDED.file_id" in out
    assert "updated_at = EXCLUDED.updated_at" in out
    assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?," in out
    # julianday rewritten for VALUES clause
    assert "julianday" not in out.lower()
    assert "EXTRACT(JULIAN FROM CURRENT_TIMESTAMP)" in out


def test_code_chunk_sqlite_statement_is_insert_or_replace() -> None:
    """SQLite / universal client path keeps INSERT OR REPLACE (driver translates on PG)."""
    assert "INSERT OR REPLACE INTO code_chunks" in CODE_CHUNK_UPSERT_SQL
    assert "chunk_uuid" in CODE_CHUNK_UPSERT_SQL


def test_code_chunk_upsert_norm_matches_postgres_driver_lookup() -> None:
    """``postgres_run`` norm key must stay aligned with ``code_chunk_sql`` (single source)."""
    from code_analysis.core.database_driver_pkg.drivers import postgres_run

    assert (
        postgres_run._CODE_CHUNKS_INSERT_OR_REPLACE_NORM
        == code_chunk_upsert_norm_for_postgres_adapter()
    )


def test_build_code_chunk_upsert_batch_rejects_wrong_param_row_length() -> None:
    """Wrong-length rows must fail before execute_batch (clear, indexed message)."""
    from code_analysis.core.database.code_chunk_sql import (
        CODE_CHUNK_UPSERT_PARAM_COUNT,
        CODE_CHUNK_UPSERT_PARAM_ORDER,
        build_code_chunk_upsert_batch,
    )

    short = (1,) * (CODE_CHUNK_UPSERT_PARAM_COUNT - 1)
    with pytest.raises(ValueError, match="code_chunk upsert param row 0") as exc:
        build_code_chunk_upsert_batch([short])
    msg = str(exc.value)
    assert str(CODE_CHUNK_UPSERT_PARAM_COUNT) in msg
    assert CODE_CHUNK_UPSERT_PARAM_ORDER[0] in msg

    ok_row = (1,) * CODE_CHUNK_UPSERT_PARAM_COUNT
    long = (1,) * (CODE_CHUNK_UPSERT_PARAM_COUNT + 1)
    with pytest.raises(ValueError, match=r"param row 1") as exc2:
        build_code_chunk_upsert_batch([ok_row, long])
    assert "row 1" in str(exc2.value).lower()


def test_build_code_chunk_upsert_batch_adapts_to_postgres_without_syntax_error() -> (
    None
):
    """Batch built from portable SQL must survive PostgreSQL DML adaptation."""
    from code_analysis.core.database.code_chunk_sql import build_code_chunk_upsert_batch

    row = (
        "30000000-0000-4000-8000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-4000-8000-000000000099",
        "DocBlock",
        "hello",
        1,
        None,
        None,
        None,
        None,
        5,
        None,
        None,
        None,
        1,
        "Module",
        "file_docstring",
        0,
    )
    ops = build_code_chunk_upsert_batch([row])
    assert len(ops) == 1
    sql, params = ops[0]
    assert "?" in sql
    pg_sql = _adapt_sqlite_dml_for_postgres(sql)
    assert "INSERT OR REPLACE" not in pg_sql
    assert "ON CONFLICT (chunk_uuid)" in pg_sql
    assert (
        "?" in pg_sql
    )  # ``?`` → ``%s`` happens at bind layer, not in _adapt_sqlite_dml_for_postgres
    assert len(params) == 19


def test_legacy_reembed_worker_path_removed() -> None:
    """Chunk-only vectorization owns embedding fill; legacy SVO re-embed is gone."""
    legacy_name = "process_chunks" + "_missing_embedding_params"
    assert not hasattr(batch_processor, legacy_name)
