"""
Regression: export_graph call_graph paginated usages + large JSON spill to file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.ast import graph as graph_module
from code_analysis.commands.ast.graph import ExportGraphMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.database import CodeDatabase
from code_analysis.core.database.base import create_driver_config_for_worker


class _DBWithDisconnect:
    """CodeDatabase has close(); MCP commands call disconnect() like DatabaseClient."""

    def __init__(self, inner: CodeDatabase) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def disconnect(self) -> None:
        self._inner.close()


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def project_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir: Path) -> Any:
    db_path = temp_dir / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path, driver_type="sqlite", backup_dir=temp_dir / "backups"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    yield db
    db.close()


@pytest.fixture
def test_project(test_db: CodeDatabase, temp_dir: Path, project_id: str) -> str:
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), temp_dir.name),
    )
    test_db._commit()
    return project_id


def _uuid4() -> str:
    return str(uuid.uuid4())


def _seed_minimal_call_graph(
    test_db: CodeDatabase, test_project: str, temp_dir: Path, n_usages: int
) -> None:
    path = temp_dir / "caller.py"
    path.write_text("# x", encoding="utf-8")
    test_db._execute(
        """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
           VALUES (?, ?, 1, 0, 0)""",
        (test_project, str(path)),
    )
    test_db._commit()
    fid = test_db._lastrowid()
    cid = _uuid4()
    test_db._execute(
        "INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (fid, "Target", 1, None, "[]", cid),
    )
    test_db._commit()
    for line in range(1, n_usages + 1):
        test_db._execute(
            "INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fid, line, "ref", "class", "Target", None),
        )
    test_db._commit()


@pytest.mark.asyncio
async def test_call_graph_paginates_usages(
    monkeypatch: pytest.MonkeyPatch,
    test_db: CodeDatabase,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_minimal_call_graph(test_db, test_project, temp_dir, n_usages=5)
    monkeypatch.setattr(graph_module, "EXPORT_GRAPH_USAGES_PAGE_SIZE", 2)

    calls: list[int] = []

    def counting_execute(sql: str, params: Any = None) -> Any:
        s = sql.upper()
        if "FROM USAGES" in s and "USAGE_ROW_ID" in s:
            calls.append(1)
        return orig_execute(sql, params)

    orig_execute = test_db.execute
    test_db.execute = counting_execute  # type: ignore[assignment]

    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command.get_shared_database",
        lambda: _DBWithDisconnect(test_db),
    )
    monkeypatch.setattr(
        BaseMCPCommand,
        "_resolve_project_root",
        staticmethod(lambda _pid: temp_dir.resolve()),
    )
    monkeypatch.setattr(
        BaseMCPCommand,
        "_get_raw_config",
        staticmethod(
            lambda: {"code_analysis": {"batch_output_dir": str(temp_dir / "out")}}
        ),
    )

    cmd = ExportGraphMCPCommand()
    res = await cmd.execute(
        test_project, graph_type="call_graph", format="json", limit=100
    )
    assert isinstance(res, SuccessResult)
    data = res.data
    assert data is not None
    assert data.get("edge_count") == 5
    # Three non-empty pages + one terminal empty fetch (keyset pagination).
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_json_export_spills_when_over_inline_limit(
    monkeypatch: pytest.MonkeyPatch,
    test_db: CodeDatabase,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_minimal_call_graph(test_db, test_project, temp_dir, n_usages=1)
    out_sub = temp_dir / "batch_out"
    monkeypatch.setattr(
        graph_module,
        "EXPORT_GRAPH_MAX_INLINE_JSON_BYTES",
        32,
    )
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command.get_shared_database",
        lambda: _DBWithDisconnect(test_db),
    )
    monkeypatch.setattr(
        BaseMCPCommand,
        "_resolve_project_root",
        staticmethod(lambda _pid: temp_dir.resolve()),
    )
    monkeypatch.setattr(
        BaseMCPCommand,
        "_get_raw_config",
        staticmethod(lambda: {"code_analysis": {"batch_output_dir": str(out_sub)}}),
    )

    cmd = ExportGraphMCPCommand()
    res = await cmd.execute(
        test_project, graph_type="call_graph", format="json", limit=100
    )
    assert isinstance(res, SuccessResult)
    data = res.data
    assert data is not None
    assert data.get("inline") is False
    assert "nodes" not in data
    op = data.get("output_file")
    assert isinstance(op, str)
    p = Path(op)
    assert p.is_file()
    raw = p.read_bytes()
    outer = json.loads(raw.decode("utf-8"))
    assert outer["format"] == "json"
    assert outer["edge_count"] == 1
    assert isinstance(outer["nodes"], list)
    assert isinstance(outer["edges"], list)


@pytest.mark.asyncio
async def test_json_export_stays_inline_below_limit(
    monkeypatch: pytest.MonkeyPatch,
    test_db: CodeDatabase,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_minimal_call_graph(test_db, test_project, temp_dir, n_usages=1)
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command.get_shared_database",
        lambda: _DBWithDisconnect(test_db),
    )
    monkeypatch.setattr(
        BaseMCPCommand,
        "_resolve_project_root",
        staticmethod(lambda _pid: temp_dir.resolve()),
    )
    monkeypatch.setattr(
        BaseMCPCommand,
        "_get_raw_config",
        staticmethod(
            lambda: {"code_analysis": {"batch_output_dir": str(temp_dir / "out")}}
        ),
    )

    cmd = ExportGraphMCPCommand()
    res = await cmd.execute(
        test_project, graph_type="call_graph", format="json", limit=100
    )
    assert isinstance(res, SuccessResult)
    data = res.data
    assert data is not None
    assert data.get("inline") is None
    assert "nodes" in data
    assert data.get("edge_count") == 1
