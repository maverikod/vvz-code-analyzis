"""Tests for rotate_all_logs and rotate_worker_logs backup_count validation."""

from __future__ import annotations

import pytest

from code_analysis.commands.log_viewer_mcp_commands.rotate_all_logs import (
    RotateAllLogsMCPCommand,
)
from code_analysis.commands.log_viewer_mcp_commands.rotate_worker_logs import (
    RotateWorkerLogsMCPCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult


@pytest.fixture(params=["rotate_all", "rotate_worker"])
def cmd(
    request: pytest.FixtureRequest,
) -> RotateAllLogsMCPCommand | RotateWorkerLogsMCPCommand:
    """Return cmd."""
    if request.param == "rotate_all":
        return RotateAllLogsMCPCommand()
    return RotateWorkerLogsMCPCommand()


def test_validate_params_accepts_backup_count_in_range(
    cmd: RotateAllLogsMCPCommand | RotateWorkerLogsMCPCommand,
) -> None:
    """Verify test validate params accepts backup count in range."""
    out = cmd.validate_params({"backup_count": 10})
    assert out["backup_count"] == 10


@pytest.mark.parametrize("backup_count", [0, -1, 100, 500])
def test_validate_params_rejects_backup_count_out_of_range(
    cmd: RotateAllLogsMCPCommand | RotateWorkerLogsMCPCommand,
    backup_count: int,
) -> None:
    """Verify test validate params rejects backup count out of range."""
    with pytest.raises(ValidationError, match="backup_count") as exc_info:
        cmd.validate_params({"backup_count": backup_count})
    assert exc_info.value.field == "backup_count"


@pytest.mark.asyncio
async def test_rotate_all_logs_execute_rejects_backup_count_out_of_range() -> None:
    """Verify test rotate all logs execute rejects backup count out of range."""
    cmd = RotateAllLogsMCPCommand()
    result = await cmd.execute(backup_count=0)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "backup_count" in result.message


@pytest.mark.asyncio
async def test_rotate_worker_logs_execute_rejects_backup_count_out_of_range() -> None:
    """Verify test rotate worker logs execute rejects backup count out of range."""
    cmd = RotateWorkerLogsMCPCommand()
    result = await cmd.execute(log_path="/tmp/nonexistent.log", backup_count=100)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "backup_count" in result.message
