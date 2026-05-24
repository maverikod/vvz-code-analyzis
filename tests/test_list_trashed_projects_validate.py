"""Tests for list_trashed_projects parameter validation."""

from __future__ import annotations

import pytest

from code_analysis.commands.project_management_mcp_commands.list_trashed_projects import (
    ListTrashedProjectsMCPCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult


def test_list_trashed_projects_validate_params_rejects_unknown_param() -> None:
    cmd = ListTrashedProjectsMCPCommand()
    with pytest.raises(ValidationError, match="unknown parameter"):
        cmd.validate_params({"__unknown_param__": "x"})


def test_list_trashed_projects_validate_params_accepts_trash_dir() -> None:
    cmd = ListTrashedProjectsMCPCommand()
    out = cmd.validate_params({"trash_dir": "/tmp/trash"})
    assert out["trash_dir"] == "/tmp/trash"


def test_list_trashed_projects_validate_params_accepts_empty_params() -> None:
    cmd = ListTrashedProjectsMCPCommand()
    out = cmd.validate_params({})
    assert out == {}


@pytest.mark.asyncio
async def test_list_trashed_projects_execute_rejects_unknown_param() -> None:
    cmd = ListTrashedProjectsMCPCommand()
    result = await cmd.execute(__unknown_param__="x")
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "unknown parameter" in result.message.lower()
