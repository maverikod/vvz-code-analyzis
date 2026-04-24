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


def test_build_status_ops_batch_length_matches_documented_indices() -> None:
    """Guards against dropping the leading projects COUNT query (regression)."""
    assert len(build_status_ops("sqlite_proxy")) == 17
    assert build_status_ops("sqlite_proxy")[0][0].strip().startswith("SELECT COUNT")
