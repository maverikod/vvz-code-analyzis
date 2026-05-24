"""Tests for list_projects parameter validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_management_mcp_commands.list_projects import (
    ListProjectsMCPCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult

_VALID_WATCH_DIR = "550e8400-e29b-41d4-a716-446655440000"


def test_list_projects_validate_params_rejects_unknown_param() -> None:
    cmd = ListProjectsMCPCommand()
    with pytest.raises(ValidationError, match="unknown parameter"):
        cmd.validate_params({"__unknown_param__": "x"})


def test_list_projects_validate_params_rejects_unknown_watched_dir_id() -> None:
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    mock_db.select.return_value = []
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        with pytest.raises(ValidationError, match="not found"):
            ListProjectsMCPCommand().validate_params(
                {"watched_dir_id": _VALID_WATCH_DIR}
            )


@pytest.mark.asyncio
async def test_list_projects_execute_rejects_unknown_param() -> None:
    cmd = ListProjectsMCPCommand()
    result = await cmd.execute(__unknown_param__="x")
    assert isinstance(result, ErrorResult)
    assert "unknown parameter" in result.message.lower()


@pytest.mark.asyncio
async def test_list_projects_execute_rejects_unknown_watched_dir_id() -> None:
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    mock_db.select.return_value = []
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        result = await ListProjectsMCPCommand().execute(watched_dir_id=_VALID_WATCH_DIR)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "not found" in result.message.lower()
