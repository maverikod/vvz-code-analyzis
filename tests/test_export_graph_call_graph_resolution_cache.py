"""
Regression / integration: export_graph call_graph counts edges with DatabaseClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.ast.graph import ExportGraphMCPCommand
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers
from tests.sqlite_legacy_schema_bootstrap import bootstrap_sqlite_schema_paths


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def project_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir: Path) -> Any:
    """Schema via legacy bootstrap; RPCH tests use reopen with pkg driver."""
    db_path = temp_dir / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path,
        driver_type="sqlite",
        backup_dir=temp_dir / "backups",
    )
    path_str, backup_dir = bootstrap_sqlite_schema_paths(
        driver_config,
        default_backup_dir=str(temp_dir / "backups"),
    )
    driver = create_driver(
        "sqlite",
        {"path": path_str, "backup_dir": backup_dir},
    )
    rpc = InProcessRpcClient(RPCHandlers(driver))
    db = DatabaseClient(rpc_client=rpc, driver_type="sqlite")
    db.connect()
    try:
        yield db
    finally:
        db.disconnect()
        driver.disconnect()


@pytest.fixture
def test_project(test_db: DatabaseClient, temp_dir: Path, project_id: str) -> str:
    test_db.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir.resolve()), temp_dir.name),
    )
    return project_id


def _uuid4() -> str:
    return str(uuid.uuid4())


def _insert_file(test_db: DatabaseClient, test_project: str, path: Path) -> str:
    fid = str(uuid.uuid4())
    test_db.execute(
        """INSERT INTO files (id, project_id, path, relative_path, lines, last_modified, has_docstring)
           VALUES (?, ?, ?, ?, 1, 0, 0)""",
        (fid, test_project, str(path), path.name),
    )
    return fid


def _insert_class(
    test_db: DatabaseClient, file_id: str, name: str, cst_node_id: str
) -> None:
    cid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO classes (id, file_id, name, line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cid, file_id, name, 1, None, "[]", cst_node_id),
    )


def _insert_usage(
    test_db: DatabaseClient,
    file_id: str,
    line: int,
    target_name: str,
) -> None:
    uid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO usages (id, file_id, line, usage_type, target_type, target_name, target_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uid, file_id, line, "ref", "class", target_name, None),
    )


def _seed_repeated_usages_same_target(
    test_db: DatabaseClient, test_project: str, temp_dir: Path, n_usages: int
) -> None:
    path = temp_dir / "caller.py"
    path.write_text("# x", encoding="utf-8")
    fid = _insert_file(test_db, test_project, path)
    _insert_class(test_db, fid, "Target", _uuid4())
    for line in range(1, n_usages + 1):
        _insert_usage(test_db, fid, line, "Target")


def _seed_two_callers_one_target(
    test_db: DatabaseClient, test_project: str, temp_dir: Path
) -> None:
    """Two files each with one usage of ``Target`` (distinct ``usage_file_id``, same name)."""
    for name in ("caller_a.py", "caller_b.py"):
        p = temp_dir / name
        p.write_text("# x", encoding="utf-8")
        fid = _insert_file(test_db, test_project, p)
        _insert_class(test_db, fid, "Target", _uuid4())
        _insert_usage(test_db, fid, 1, "Target")


def _seed_missing_target_repeated(
    test_db: DatabaseClient, test_project: str, temp_dir: Path, n_usages: int
) -> None:
    path = temp_dir / "caller.py"
    path.write_text("# x", encoding="utf-8")
    fid = _insert_file(test_db, test_project, path)
    for line in range(1, n_usages + 1):
        _insert_usage(test_db, fid, line, "NoSuchClass")


@pytest.mark.asyncio
async def test_call_graph_emit_edges_for_repeated_targets(
    monkeypatch: pytest.MonkeyPatch,
    test_db: DatabaseClient,
    test_project: str,
    temp_dir: Path,
) -> None:
    n = 10
    _seed_repeated_usages_same_target(test_db, test_project, temp_dir, n_usages=n)
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command.get_shared_database",
        lambda: test_db,
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


@pytest.mark.asyncio
async def test_call_graph_emit_edges_two_callers_same_symbol(
    monkeypatch: pytest.MonkeyPatch,
    test_db: DatabaseClient,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_two_callers_one_target(test_db, test_project, temp_dir)
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command.get_shared_database",
        lambda: test_db,
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


@pytest.mark.asyncio
async def test_call_graph_unknown_target_symbol_emits_edges(
    monkeypatch: pytest.MonkeyPatch,
    test_db: DatabaseClient,
    test_project: str,
    temp_dir: Path,
) -> None:
    _seed_missing_target_repeated(test_db, test_project, temp_dir, n_usages=7)
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command.get_shared_database",
        lambda: test_db,
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
    assert res.data.get("edge_count") == 7
