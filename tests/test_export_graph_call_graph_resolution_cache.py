"""
Regression: call_graph export memoizes resolve_usage_target_cst_node_id per export.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.ast import graph as graph_module
from code_analysis.commands.ast.graph import ExportGraphMCPCommand
from code_analysis.commands.ast.graph_entity_nodes import (
    resolve_usage_target_cst_node_id,
)
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


def _seed_repeated_usages_same_target(
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


def _seed_two_callers_one_target(
    test_db: CodeDatabase, test_project: str, temp_dir: Path
) -> None:
    """Two files each with one usage of ``Target`` (distinct ``usage_file_id``, same name)."""
    for name in ("caller_a.py", "caller_b.py"):
        p = temp_dir / name
        p.write_text("# x", encoding="utf-8")
        test_db._execute(
            """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, 1, 0, 0)""",
            (test_project, str(p)),
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
        test_db._execute(
            "INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fid, 1, "ref", "class", "Target", None),
        )
        test_db._commit()


def _seed_missing_target_repeated(
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
    for line in range(1, n_usages + 1):
        test_db._execute(
            "INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fid, line, "ref", "class", "NoSuchClass", None),
        )
    test_db._commit()


@pytest.mark.asyncio
async def test_identical_usage_keys_call_resolve_once(
    monkeypatch: pytest.MonkeyPatch,
    test_db: CodeDatabase,
    test_project: str,
    temp_dir: Path,
) -> None:
    n = 10
    _seed_repeated_usages_same_target(test_db, test_project, temp_dir, n_usages=n)
    resolve_calls = 0

    def counting_resolve(*args: Any, **kwargs: Any) -> Any:
        nonlocal resolve_calls
        resolve_calls += 1
        return resolve_usage_target_cst_node_id(*args, **kwargs)

    monkeypatch.setattr(
        graph_module,
        "resolve_usage_target_cst_node_id",
        counting_resolve,
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
    assert data.get("edge_count") == n
    assert resolve_calls == 1


@pytest.mark.asyncio
async def test_distinct_usage_file_ids_still_resolve_separately(
    monkeypatch: pytest.MonkeyPatch,
    test_db: CodeDatabase,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_two_callers_one_target(test_db, test_project, temp_dir)
    resolve_calls = 0

    def counting_resolve(*args: Any, **kwargs: Any) -> Any:
        nonlocal resolve_calls
        resolve_calls += 1
        return resolve_usage_target_cst_node_id(*args, **kwargs)

    monkeypatch.setattr(
        graph_module,
        "resolve_usage_target_cst_node_id",
        counting_resolve,
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
        staticmethod(
            lambda: {"code_analysis": {"batch_output_dir": str(temp_dir / "out")}}
        ),
    )

    cmd = ExportGraphMCPCommand()
    res = await cmd.execute(
        test_project, graph_type="call_graph", format="json", limit=100
    )
    assert isinstance(res, SuccessResult)
    assert res.data is not None
    assert res.data.get("edge_count") == 2
    assert resolve_calls == 2


@pytest.mark.asyncio
async def test_cached_none_misses_do_not_requery(
    monkeypatch: pytest.MonkeyPatch,
    test_db: CodeDatabase,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_missing_target_repeated(test_db, test_project, temp_dir, n_usages=7)
    resolve_calls = 0

    def counting_resolve(*args: Any, **kwargs: Any) -> Any:
        nonlocal resolve_calls
        resolve_calls += 1
        return resolve_usage_target_cst_node_id(*args, **kwargs)

    monkeypatch.setattr(
        graph_module,
        "resolve_usage_target_cst_node_id",
        counting_resolve,
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
        staticmethod(
            lambda: {"code_analysis": {"batch_output_dir": str(temp_dir / "out")}}
        ),
    )

    cmd = ExportGraphMCPCommand()
    res = await cmd.execute(
        test_project, graph_type="call_graph", format="json", limit=100
    )
    assert isinstance(res, SuccessResult)
    assert res.data is not None
    assert res.data.get("edge_count") == 0
    assert resolve_calls == 1
