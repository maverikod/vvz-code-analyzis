"""
Tests for change_project_id: duplicate new id and DB failure rollback.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.project_management_mcp_commands.change_project_id import (
    ChangeProjectIdMCPCommand,
)
from code_analysis.core.database_client.objects.project import Project
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


@pytest.fixture
def cmd() -> ChangeProjectIdMCPCommand:
    """Return cmd."""
    return ChangeProjectIdMCPCommand()


@pytest.mark.asyncio
async def test_duplicate_new_project_id_fails_before_file_change(
    cmd: ChangeProjectIdMCPCommand, tmp_path: Path
) -> None:
    """Verify test duplicate new project id fails before file change."""
    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    root = tmp_path / "myprj"
    root.mkdir()
    projectid = root / "projectid"
    original = json.dumps({"id": old_id, "description": "keep"}) + "\n"
    projectid.write_text(original, encoding="utf-8")

    other = Project(
        id=new_id,
        root_path=str(tmp_path / "other_prj"),
        name="other",
    )

    pre_db = MagicMock()
    pre_db.disconnect = MagicMock()

    with (
        patch.object(cmd, "_resolve_project_root", return_value=root),
        patch.object(
            ChangeProjectIdMCPCommand,
            "_open_database_from_config",
            return_value=pre_db,
        ),
        patch(
            "code_analysis.commands.project_management_mcp_commands."
            "change_project_id.get_project",
            return_value=other,
        ),
    ):
        result = await cmd.execute(
            project_id=old_id,
            new_project_id=new_id,
            update_database=True,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "DUPLICATE_PROJECT_ID"
    assert projectid.read_text(encoding="utf-8") == original
    assert pre_db.disconnect.called


@pytest.mark.asyncio
async def test_database_error_restores_projectid_file(
    cmd: ChangeProjectIdMCPCommand, tmp_path: Path
) -> None:
    """Verify test database error restores projectid file."""
    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())
    root = tmp_path / "myprj"
    root.mkdir()
    projectid = root / "projectid"
    original = json.dumps({"id": old_id, "description": "x"}) + "\n"
    projectid.write_text(original, encoding="utf-8")

    pre_db = MagicMock()
    pre_db.disconnect = MagicMock()

    main_db = MagicMock()
    main_db.disconnect = MagicMock()
    main_db.select = MagicMock(return_value=[{"id": old_id}])
    main_db.execute = MagicMock(side_effect=RuntimeError("simulated DB failure"))

    with (
        patch.object(cmd, "_resolve_project_root", return_value=root),
        patch.object(
            ChangeProjectIdMCPCommand,
            "_open_database_from_config",
            side_effect=[pre_db, main_db],
        ),
        patch.object(
            cmd, "_resolve_config_path", return_value=tmp_path / "config.json"
        ),
        patch(
            "code_analysis.core.storage_paths.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
        ),
        patch(
            "code_analysis.commands.project_management_mcp_commands."
            "change_project_id.get_project",
            return_value=None,
        ),
    ):
        result = await cmd.execute(
            project_id=old_id,
            new_project_id=new_id,
            update_database=True,
        )

    assert isinstance(result, ErrorResult)
    assert "simulated DB failure" in result.message
    assert projectid.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_same_id_description_only_still_succeeds(
    cmd: ChangeProjectIdMCPCommand, tmp_path: Path
) -> None:
    """Verify test same id description only still succeeds."""
    pid = str(uuid.uuid4())
    root = tmp_path / "myprj"
    root.mkdir()
    projectid = root / "projectid"
    projectid.write_text(
        json.dumps({"id": pid, "description": "old"}) + "\n",
        encoding="utf-8",
    )

    main_db = MagicMock()
    main_db.disconnect = MagicMock()
    main_db.select = MagicMock(return_value=[{"id": pid}])
    main_db.execute = MagicMock(return_value={"affected_rows": 1})

    with (
        patch.object(cmd, "_resolve_project_root", return_value=root),
        patch.object(
            ChangeProjectIdMCPCommand,
            "_open_database_from_config",
            return_value=main_db,
        ),
        patch.object(
            cmd, "_resolve_config_path", return_value=tmp_path / "config.json"
        ),
        patch(
            "code_analysis.core.storage_paths.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
        ),
    ):
        result = await cmd.execute(
            project_id=pid,
            new_project_id=pid,
            description="new_desc",
            update_database=True,
        )

    assert isinstance(result, SuccessResult)
    data = json.loads(projectid.read_text(encoding="utf-8"))
    assert data["description"] == "new_desc"
    assert data["id"] == pid
