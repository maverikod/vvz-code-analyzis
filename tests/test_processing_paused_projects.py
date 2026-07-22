"""
Tests for projects.processing_paused: schema, discovery SQL, and Project model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_client.objects.project import Project
from code_analysis.core.indexing_worker_pkg.processing import (
    INDEXING_PROJECT_DISCOVERY_SQL,
)
from code_analysis.core.vectorization_worker_pkg.processing_cycle import (
    PROJECTS_PENDING_SQL,
)

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
    """Verify test project model processing paused roundtrip."""
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
    """Verify test vectorization projects sql filters processing paused."""
    assert "processing_paused" in PROJECTS_PENDING_SQL


def test_indexing_discovery_sql_filters_processing_paused() -> None:
    """Verify test indexing discovery sql filters processing paused."""
    assert "processing_paused" in INDEXING_PROJECT_DISCOVERY_SQL
    assert "INNER JOIN projects" in INDEXING_PROJECT_DISCOVERY_SQL
