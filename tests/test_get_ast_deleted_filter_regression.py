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


class _ObjectWithData:
    def __init__(self, data: Any) -> None:
        self.data = data


class _RowMapping:
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def keys(self):
        return self._data.keys()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]


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


def test_get_ast_searchable_index_when_db_execute_returns_dict_data() -> None:
    db = MagicMock()
    db.execute.return_value = {
        "data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]
    }

    ok = GetASTMCPCommand._has_searchable_ast_index(db, project_id="p1", file_id=42)

    assert ok is True


def test_get_ast_searchable_index_when_db_execute_returns_sequence_rows() -> None:
    db = MagicMock()
    db.execute.return_value = [(0, 1, 0)]

    ok = GetASTMCPCommand._has_searchable_ast_index(db, project_id="p1", file_id=42)

    assert ok is True


def test_get_ast_searchable_index_when_db_execute_returns_object_rows() -> None:
    db = MagicMock()
    db.execute.return_value = _ObjectWithData(
        [_RowMapping({"classes_count": 0, "functions_count": 0, "methods_count": 1})]
    )

    ok = GetASTMCPCommand._has_searchable_ast_index(db, project_id="p1", file_id=42)

    assert ok is True


@pytest.mark.asyncio
async def test_get_ast_matches_search_ast_nodes_indexed_file(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 42,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
    ]
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

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["file_id"] == 42
    assert result.data["file_path"] == target_rel


@pytest.mark.asyncio
async def test_get_ast_project_relative_and_absolute_path_same_result(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 55,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
        {
            "data": [
                {
                    "id": 55,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
    ]
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
        relative_result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            include_json=False,
        )
        absolute_result = await cmd.execute(
            project_id="p1",
            file_path=str(target_abs.resolve()),
            include_json=False,
        )

    assert relative_result.data["success"] is True
    assert absolute_result.data["success"] is True
    assert relative_result.data["file_id"] == absolute_result.data["file_id"]


@pytest.mark.asyncio
async def test_get_ast_returns_success_for_searchable_file_without_ast_tree(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 123,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
    ]
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
        result_no_json = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            include_json=False,
        )

    assert isinstance(result_no_json, SuccessResult)
    assert result_no_json.data["success"] is True
    assert result_no_json.data["file_id"] == 123
    assert "ast" not in result_no_json.data


@pytest.mark.asyncio
async def test_get_ast_returns_success_with_json_for_searchable_file_without_ast_tree(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "proj"
    target_rel = "ai_admin/commands/base.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("class AIAdminCommand:\n    pass\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 123,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
    ]
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
        result_with_json = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            include_json=True,
        )

    assert isinstance(result_with_json, SuccessResult)
    assert result_with_json.data["success"] is True
    assert result_with_json.data["file_id"] == 123
    assert "ast" in result_with_json.data
    assert isinstance(result_with_json.data["ast"], str)


def test_get_ast_source_does_not_use_coalesce_deleted_filter() -> None:
    source_text = Path("code_analysis/commands/ast/get_ast.py").read_text(
        encoding="utf-8"
    )
    assert "COALESCE(f.deleted, 0)" not in source_text


@pytest.mark.asyncio
async def test_get_ast_existing_file_without_any_index_returns_ast_not_indexed(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "proj"
    target_rel = "pkg/no_index.py"
    target_abs = project_root / target_rel
    target_abs.parent.mkdir(parents=True)
    target_abs.write_text("x = 1\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 99,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 0, "functions_count": 0, "methods_count": 0}]},
    ]
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
    assert result.code == "AST_NOT_INDEXED"


@pytest.mark.asyncio
async def test_get_ast_missing_file_returns_file_not_found(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)

    mock_db = MagicMock()
    mock_db.execute.return_value = {"data": []}
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
            file_path="pkg/missing.py",
            include_json=False,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "FILE_NOT_FOUND"
