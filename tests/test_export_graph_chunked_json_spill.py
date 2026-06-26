"""
Integration: export_graph call_graph JSON shape + usages query via DatabaseClient.

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
    """Return temp dir."""
    return tmp_path


@pytest.fixture
def project_id() -> str:
    """Return project id."""
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir: Path) -> Any:
    """Verify test db."""
    driver_config = create_driver_config_for_worker(
        temp_dir / "test.db",
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
    """Verify test project."""
    test_db.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir.resolve()), temp_dir.name),
    )
    return project_id


def _uuid4() -> str:
    """Return uuid4."""
    return str(uuid.uuid4())


def _insert_file(test_db: DatabaseClient, test_project: str, path: Path) -> str:
    """Return insert file."""
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
    """Return insert class."""
    cid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO classes (id, file_id, name, line, docstring, bases, cst_node_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (cid, file_id, name, 1, None, "[]", cst_node_id),
    )


def _insert_usage(
    test_db: DatabaseClient, file_id: str, line: int, target_name: str
) -> None:
    """Return insert usage."""
    uid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO usages (id, file_id, line, usage_type, target_type, target_name, target_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uid, file_id, line, "ref", "class", target_name, None),
    )


def _seed_minimal_call_graph(
    test_db: DatabaseClient, test_project: str, temp_dir: Path, n_usages: int
) -> None:
    """Return seed minimal call graph."""
    path = temp_dir / "caller.py"
    path.write_text("# x", encoding="utf-8")
    fid = _insert_file(test_db, test_project, path)
    _insert_class(test_db, fid, "Target", _uuid4())
    for line in range(1, n_usages + 1):
        _insert_usage(test_db, fid, line, "Target")


@pytest.mark.asyncio
async def test_call_graph_single_usages_query(
    monkeypatch: pytest.MonkeyPatch,
    test_db: DatabaseClient,
    test_project: str,
    temp_dir: Path,
) -> None:
    """Current exporter loads usages with one JOIN query (no keyset pagination)."""
    _seed_minimal_call_graph(test_db, test_project, temp_dir, n_usages=5)

    calls: list[int] = []
    orig_execute = test_db.execute

    def counting_execute(sql: str, params: Any = None, **kwargs: Any) -> dict[str, Any]:
        """Return counting execute."""
        if "FROM USAGES" in sql.upper():
            calls.append(1)
        return orig_execute(sql, params, **kwargs)

    test_db.execute = counting_execute  # type: ignore[assignment]

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
    assert data.get("edge_count") == 5
    assert sum(calls) == 1


@pytest.mark.asyncio
async def test_call_graph_json_success_payload(
    monkeypatch: pytest.MonkeyPatch,
    test_db: DatabaseClient,
    test_project: str,
    temp_dir: Path,
) -> None:
    """JSON export returns nodes, edges, and entity_payload inline."""
    _seed_minimal_call_graph(test_db, test_project, temp_dir, n_usages=1)
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
    assert data.get("format") == "json"
    assert data.get("edge_count") == 1
    assert isinstance(data.get("nodes"), list)
    assert isinstance(data.get("edges"), list)
    assert isinstance(data.get("entity_nodes"), list)
