"""Regression: delete logical write removes project-scoped issues and dual-FK rows."""

import asyncio
from unittest.mock import MagicMock

from code_analysis.commands.clear_project_data_impl import (
    _pair_entity_cross_ref_delete,
    _pair_issues_delete,
    build_delete_project_full_clear_batch,
    _clear_project_data_impl,
    mark_project_deleted_impl,
)
from code_analysis.core.sql_portable import database_has_sqlite_code_content_fts


def test_database_has_sqlite_code_content_fts_by_driver() -> None:
    pg = MagicMock()
    pg._driver_type = "postgres"
    assert database_has_sqlite_code_content_fts(pg) is False
    sl = MagicMock()
    sl._driver_type = "sqlite_proxy"
    assert database_has_sqlite_code_content_fts(sl) is True
    bare = MagicMock()
    assert database_has_sqlite_code_content_fts(bare) is True


def test_full_clear_batch_skips_fts_when_disabled() -> None:
    ops = build_delete_project_full_clear_batch(
        "proj-no-fts", include_code_content_fts=False
    )
    assert not any("code_content_fts" in sql for sql, _ in ops)


def test_full_clear_batch_issues_delete_uses_project_id_subqueries() -> None:
    ops = build_delete_project_full_clear_batch("proj-issues")
    issues_sql = [sql for sql, _ in ops if "DELETE FROM issues" in sql]
    assert len(issues_sql) == 1
    assert "project_id = ?" in issues_sql[0]
    assert "SELECT id FROM files WHERE project_id = ?" in issues_sql[0]


def test_full_clear_batch_sweeps_dual_fk_tables_by_project_id() -> None:
    pid = "proj-dual-fk"
    ops = build_delete_project_full_clear_batch(pid)
    pairs = [(sql, params) for sql, params in ops]
    assert ("DELETE FROM code_chunks WHERE project_id = ?", (pid,)) in pairs
    assert ("DELETE FROM ast_trees WHERE project_id = ?", (pid,)) in pairs
    assert ("DELETE FROM cst_trees WHERE project_id = ?", (pid,)) in pairs
    assert (
        "DELETE FROM comprehensive_analysis_results WHERE project_id = ?",
        (pid,),
    ) in pairs


def test_delete_batch_each_statement_param_count_matches_placeholders() -> None:
    """Every ? in SQL must have a bound parameter (SQLite binding rules)."""
    pid = "00000000-0000-4000-8000-000000000001"
    for sql, params in build_delete_project_full_clear_batch(pid):
        assert sql.count("?") == len(params), (sql[:80], sql.count("?"), len(params))


def test_issues_and_entity_cross_ref_helpers_param_counts() -> None:
    pid = "p"
    for sql, params in (_pair_issues_delete(pid), _pair_entity_cross_ref_delete(pid)):
        assert sql.count("?") == len(params)


def test_clear_project_data_uses_single_logical_write_rpc() -> None:
    """Full DB clear must be one execute_logical_write_operation (no transaction helpers)."""

    async def _run() -> None:
        db = MagicMock()
        db._driver_type = "postgres"
        await _clear_project_data_impl(db, "proj-1")
        db.execute_logical_write_operation.assert_called_once()
        prog = db.execute_logical_write_operation.call_args[0][0]
        assert prog["batches"] and len(prog["batches"]) == 1
        stmts = [pair[0] for pair in prog["batches"][0]]
        assert not any("code_content_fts" in s for s in stmts)

    asyncio.run(_run())


def test_mark_project_deleted_uses_single_logical_write_rpc() -> None:

    async def _run() -> None:
        db = MagicMock()
        await mark_project_deleted_impl(db, "proj-2")
        db.execute_logical_write_operation.assert_called_once()
        prog = db.execute_logical_write_operation.call_args[0][0]
        stmts = [pair[0] for pair in prog["batches"][0]]
        assert any(s.startswith("UPDATE files SET deleted = 1") for s in stmts)
        assert any("UPDATE projects SET deleted = 1" in s for s in stmts)

    asyncio.run(_run())
