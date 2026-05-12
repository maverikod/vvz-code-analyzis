"""Dialect-specific SQL for get_database_status (PostgreSQL vs SQLite)."""

from __future__ import annotations

from code_analysis.commands.worker_status_mcp_commands.get_database_status_build import (
    build_status_ops,
)


def test_build_status_ops_sqlite_uses_julianday() -> None:
    ops = build_status_ops("sqlite_proxy")
    sql = " ".join(q[0] for q in ops)
    assert "julianday('now', '-1 day')" in sql
    assert "EXTRACT(JULIAN" not in sql


def test_build_status_ops_postgres_uses_extract() -> None:
    ops = build_status_ops("postgres")
    assert len(ops) == 17
    sql = " ".join(q[0] for q in ops)
    assert "EXTRACT(JULIAN FROM (CURRENT_TIMESTAMP - INTERVAL '1 day'))" in sql
    assert "julianday" not in sql


def test_build_status_ops_include_ast_aware_indexed_and_ignore_paths() -> None:
    """Status SQL treats AST as indexed progress and excludes default ignored path segments."""
    sql = " ".join(q[0] for q in build_status_ops("sqlite_proxy"))
    assert "ast_trees" in sql
    assert "/.venv/" in sql or "%/.venv/%" in sql
    assert "INNER JOIN files fl ON fl.id = cc.file_id" in sql


def test_needing_indexing_count_is_inverse_of_structural_indexed_predicate() -> None:
    """files_needing_indexing must complement files_indexed (same active + path filters)."""
    sql = " ".join(q[0] for q in build_status_ops("sqlite_proxy"))
    inv_files = (
        "AND NOT (((needs_chunking = 0 OR needs_chunking IS NULL) OR "
        "EXISTS (SELECT 1 FROM ast_trees WHERE ast_trees.file_id = files.id)))"
    )
    assert inv_files in sql.replace("\n", " ")
    inv_f = (
        "AND NOT (((f.needs_chunking = 0 OR f.needs_chunking IS NULL) OR "
        "EXISTS (SELECT 1 FROM ast_trees WHERE ast_trees.file_id = f.id)))"
    )
    assert inv_f in sql.replace("\n", " ")


def test_build_status_ops_batch_length_matches_documented_indices() -> None:
    """Guards against dropping the leading projects COUNT query (regression)."""
    assert len(build_status_ops("sqlite_proxy")) == 17
    assert build_status_ops("sqlite_proxy")[0][0].strip().startswith("SELECT COUNT")


def test_build_status_ops_pgvector_uses_embedding_vec_predicate() -> None:
    sql = " ".join(
        q[0] for q in build_status_ops("postgres", vector_ann_backend="pgvector")
    )
    assert "embedding_vec IS NOT NULL" in sql
    assert "embedding_vec IS NULL" in sql
    assert "cc.vector_id IS NOT NULL" not in sql


def test_build_status_ops_postgres_faiss_uses_vector_id_predicate() -> None:
    sql = " ".join(
        q[0] for q in build_status_ops("postgres", vector_ann_backend="faiss")
    )
    assert "cc.vector_id IS NOT NULL" in sql
    assert "embedding_vec IS NOT NULL" not in sql
