"""
Tests for projects.processing_paused: schema, discovery SQL, and Project model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.indexing_worker_pkg.processing import (
    INDEXING_PROJECT_DISCOVERY_SQL,
)
from code_analysis.core.vectorization_worker_pkg.processing_cycle import (
    PROJECTS_PENDING_SQL,
)

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_set_project_processing_paused_binds_python_bool() -> None:
    """PostgreSQL BOOLEAN rejects smallint params; execute must use True/False."""
    from code_analysis.commands.project_management_mcp_commands.set_project_processing_paused import (
        SetProjectProcessingPausedMCPCommand,
    )

    db = MagicMock()
    db.disconnect = MagicMock()
    db.execute = MagicMock()
    db.select.return_value = [{"id": _VALID_UUID, "processing_paused": True}]

    with patch.object(
        SetProjectProcessingPausedMCPCommand,
        "_open_database_from_config",
        return_value=db,
    ):
        cmd = SetProjectProcessingPausedMCPCommand()
        await cmd.execute(project_id=_VALID_UUID, processing_paused=True)

    _sql, params = db.execute.call_args[0]
    assert isinstance(params[0], bool) and params[0] is True
    assert params[1] == _VALID_UUID

    db.execute.reset_mock()
    db.select.return_value = [{"id": _VALID_UUID, "processing_paused": False}]
    with patch.object(
        SetProjectProcessingPausedMCPCommand,
        "_open_database_from_config",
        return_value=db,
    ):
        await cmd.execute(project_id=_VALID_UUID, processing_paused=False)
    _sql2, params2 = db.execute.call_args[0]
    assert isinstance(params2[0], bool) and params2[0] is False


def test_project_model_processing_paused_roundtrip() -> None:
    p = Project(
        id=_VALID_UUID,
        root_path="/tmp/r",
        processing_paused=True,
    )
    row = p.to_db_row()
    assert row.get("processing_paused") == 1
    q = Project.from_dict(
        {
            "id": p.id,
            "root_path": p.root_path,
            "processing_paused": 0,
        }
    )
    assert q.processing_paused is False


def test_vectorization_projects_sql_filters_processing_paused() -> None:
    assert "processing_paused" in PROJECTS_PENDING_SQL


def test_indexing_discovery_sql_filters_processing_paused() -> None:
    assert "processing_paused" in INDEXING_PROJECT_DISCOVERY_SQL
    assert "INNER JOIN projects" in INDEXING_PROJECT_DISCOVERY_SQL


def test_projects_table_has_processing_paused_after_sync_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "pp.db"
    client = sqlite_inprocess_database_client(db_path, backup_dir=tmp_path / "bp")
    try:
        info = client.get_table_info("projects")
        names = {col["name"] for col in info}
        assert "processing_paused" in names
    finally:
        client.disconnect()


@pytest.fixture
def pp_disc_db_client(tmp_path: Path) -> Iterator[DatabaseClient]:
    db_path = tmp_path / "disc.db"
    backup_dir = tmp_path / "disc_backups"
    original = os.environ.get("CODE_ANALYSIS_DB_WORKER")
    os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"
    db = None
    try:
        db = sqlite_inprocess_database_client(db_path, backup_dir=backup_dir)
        yield db
    finally:
        if db is not None:
            db.disconnect()
        if original is None:
            os.environ.pop("CODE_ANALYSIS_DB_WORKER", None)
        else:
            os.environ["CODE_ANALYSIS_DB_WORKER"] = original


def test_indexing_discovery_returns_no_projects_when_paused(
    pp_disc_db_client: DatabaseClient, tmp_path: Path
) -> None:
    """When processing_paused=1, discovery must not return that project_id."""
    import time

    root = tmp_path / "proj_root"
    root.mkdir()
    py_file = root / "x.py"
    py_file.write_text("x = 1\n", encoding="utf-8")

    project_id = str(uuid.uuid4())
    pp_disc_db_client.execute(
        "INSERT INTO projects (id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(root.resolve()), "pp_t"),
    )
    file_id = pp_disc_db_client.add_file(
        path=str(py_file),
        lines=1,
        last_modified=time.time(),
        has_docstring=False,
        project_id=project_id,
    )
    pp_disc_db_client.execute(
        "UPDATE files SET needs_chunking = 1 WHERE id = ?",
        (file_id,),
    )
    pp_disc_db_client.execute(
        "UPDATE projects SET processing_paused = 1 WHERE id = ?",
        (project_id,),
    )
    r = pp_disc_db_client.execute(INDEXING_PROJECT_DISCOVERY_SQL, ())
    rows = r.get("data", []) if isinstance(r, dict) else []
    ids = [row["project_id"] for row in rows] if rows else []
    assert project_id not in ids

    pp_disc_db_client.execute(
        "UPDATE projects SET processing_paused = 0 WHERE id = ?",
        (project_id,),
    )
    r2 = pp_disc_db_client.execute(INDEXING_PROJECT_DISCOVERY_SQL, ())
    rows2 = r2.get("data", []) if isinstance(r2, dict) else []
    ids2 = [row["project_id"] for row in rows2] if rows2 else []
    assert project_id in ids2
