"""
Regression tests for get_ast file lookup deleted filtering.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.ast.file_resolution import resolve_project_file_record
from code_analysis.commands.ast.get_ast import GetASTMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand


class _SQLiteAdapter:
    """Minimal DB adapter exposing execute() like DatabaseClient."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.last_sql: str = ""

    def execute(self, sql: str, params: Tuple[Any, ...]) -> Dict[str, Any]:
        self.last_sql = sql
        cur = self.conn.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
        return {"data": rows}


@pytest.mark.parametrize(
    ("deleted_value", "should_resolve"),
    [
        (0, True),
        (None, True),
        (1, False),
    ],
)
def test_get_ast_project_relative_path_postgres_deleted_filter(
    tmp_path: Path,
    deleted_value: int | None,
    should_resolve: bool,
) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            project_id TEXT NOT NULL,
            path TEXT NOT NULL,
            relative_path TEXT,
            deleted BOOLEAN
        )
        """
    )
    conn.execute(
        """
        INSERT INTO files(id, project_id, path, relative_path, deleted)
        VALUES (?, ?, ?, ?, ?)
        """,
        (7, "p1", str(target_abs.resolve()), target_rel, deleted_value),
    )
    conn.commit()

    adapter = _SQLiteAdapter(conn)
    result = resolve_project_file_record(
        db=adapter,
        project_id="p1",
        project_root=project_root,
        file_path=target_rel,
    )

    assert "COALESCE(f.deleted, 0) = 0" not in adapter.last_sql
    assert "f.deleted IS NOT TRUE" in adapter.last_sql
    assert (result["file_record"] is not None) is should_resolve
    conn.close()


@pytest.mark.asyncio
async def test_get_ast_valid_indexed_file_success(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.return_value = {
        "data": [
            {
                "id": 42,
                "path": str(target_abs.resolve()),
                "relative_path": target_rel,
                "deleted": 0,
            }
        ]
    }
    mock_db.get_ast.return_value = {"_type": "Module", "body": []}
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            include_json=False,
        )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["file_id"] == 42


@pytest.mark.asyncio
async def test_get_ast_existing_file_without_ast_not_indexed(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.return_value = {
        "data": [
            {
                "id": 99,
                "path": str(target_abs.resolve()),
                "relative_path": target_rel,
                "deleted": None,
            }
        ]
    }
    mock_db.get_ast.return_value = None
    mock_db.disconnect.return_value = None

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand, "_resolve_project_root", return_value=project_root
        ),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            include_json=False,
        )

    assert isinstance(result, ErrorResult)
    assert result.code in {"AST_NOT_INDEXED", "AST_NOT_FOUND"}
