"""Tests for list_projects (disk discovery) parameter validation."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from code_analysis.commands.project_management_mcp_commands.list_projects import (
    ListProjectsMCPCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


def _write_config(tmp_path: Path, watch_dirs: list[dict]) -> Path:
    """Return write config."""
    cfg = {"code_analysis": {"worker": {"watch_dirs": watch_dirs}}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg), encoding="utf-8")
    return config_path


def test_list_projects_validate_params_rejects_unknown_param() -> None:
    """Verify test list projects validate params rejects unknown param."""
    cmd = ListProjectsMCPCommand()
    with pytest.raises(ValidationError, match="unknown parameter"):
        cmd.validate_params({"__unknown_param__": "x"})


def test_list_projects_validate_params_rejects_unknown_watched_dir_id(
    tmp_path: Path,
) -> None:
    """Verify test list projects validate params rejects unknown watched dir id."""
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    wid = str(uuid.uuid4())
    config_path = _write_config(tmp_path, [{"id": wid, "path": str(watch_root)}])
    cmd = ListProjectsMCPCommand()
    cmd._resolve_config_path = lambda: config_path  # type: ignore[method-assign]
    with pytest.raises(ValidationError, match="not found"):
        cmd.validate_params({"watched_dir_id": str(uuid.uuid4())})


@pytest.mark.asyncio
async def test_list_projects_execute_rejects_unknown_param() -> None:
    """Verify test list projects execute rejects unknown param."""
    cmd = ListProjectsMCPCommand()
    result = await cmd.execute(__unknown_param__="x")
    assert isinstance(result, ErrorResult)
    assert "unknown parameter" in result.message.lower()


@pytest.mark.asyncio
async def test_list_projects_execute_rejects_unknown_watched_dir_id(
    tmp_path: Path,
) -> None:
    """Verify test list projects execute rejects unknown watched dir id."""
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    wid = str(uuid.uuid4())
    config_path = _write_config(tmp_path, [{"id": wid, "path": str(watch_root)}])
    cmd = ListProjectsMCPCommand()
    cmd._resolve_config_path = lambda: config_path  # type: ignore[method-assign]
    result = await cmd.execute(watched_dir_id=str(uuid.uuid4()))
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "not found" in result.message.lower()


@pytest.mark.asyncio
async def test_list_projects_command_disk_format(tmp_path: Path) -> None:
    """Verify test list projects command disk format."""
    from code_analysis.commands.command_metadata_helpers import REQUIRED_METADATA_KEYS

    watch_root = tmp_path / "tools"
    watch_root.mkdir()
    wid = str(uuid.uuid4())
    pid = str(uuid.uuid4())
    project_dir = watch_root / "my_app"
    project_dir.mkdir()
    (project_dir / "projectid").write_text(
        json.dumps(
            {
                "id": pid,
                "description": "My app",
                "processing_paused": True,
            },
            indent=4,
        )
        + "\n",
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path, [{"id": wid, "path": str(watch_root)}])

    meta = ListProjectsMCPCommand.metadata()
    for key in REQUIRED_METADATA_KEYS:
        assert key in meta, f"missing metadata key: {key}"

    cmd = ListProjectsMCPCommand()
    cmd._resolve_config_path = lambda: config_path  # type: ignore[method-assign]

    result = await cmd.execute()
    assert isinstance(result, SuccessResult)
    assert result.data["count"] == 1
    project = result.data["projects"][0]
    assert project == {
        "id": pid,
        "watch_dir": str(watch_root.resolve()),
        "name": "my_app",
        "root_path": "my_app",
        "comment": "My app",
        "watch_dir_id": wid,
        "processing_paused": True,
        "deleted": False,
        "updated_at": None,
    }
    assert "success" not in result.data
    assert "watch_dirs" not in result.data

    deleted_dir = watch_root / "trashed"
    deleted_dir.mkdir()
    (deleted_dir / "projectid").write_text(
        json.dumps({"id": str(uuid.uuid4()), "description": "gone", "deleted": True})
        + "\n",
        encoding="utf-8",
    )
    without = await cmd.execute()
    assert without.data["count"] == 1
    with_deleted = await cmd.execute(include_deleted=True)
    assert with_deleted.data["count"] == 2
