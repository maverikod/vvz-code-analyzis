"""Tests for view_worker_logs parameter normalization and bounds validation."""

from __future__ import annotations

import pytest

from code_analysis.commands.log_viewer_mcp_commands.view_worker_logs import (
    ViewWorkerLogsMCPCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult


def test_view_worker_logs_strips_dot_log_suffix_for_log_id() -> None:
    """Verify test view worker logs strips dot log suffix for log id."""
    cmd = ViewWorkerLogsMCPCommand()
    out = cmd.validate_params({"log_id": "mcp_server.log"})
    assert out["log_id"] == "mcp_server"


def test_view_worker_logs_leaves_canonical_log_id() -> None:
    """Verify test view worker logs leaves canonical log id."""
    cmd = ViewWorkerLogsMCPCommand()
    out = cmd.validate_params({"log_id": "code_analysis"})
    assert out["log_id"] == "code_analysis"


@pytest.mark.parametrize("importance_min", [-1, 11, 100])
def test_validate_params_rejects_importance_min_out_of_range(
    importance_min: int,
) -> None:
    """Verify test validate params rejects importance min out of range."""
    cmd = ViewWorkerLogsMCPCommand()
    with pytest.raises(ValidationError, match="importance_min") as exc_info:
        cmd.validate_params({"importance_min": importance_min})
    assert exc_info.value.field == "importance_min"


@pytest.mark.asyncio
async def test_execute_rejects_importance_max_out_of_range_at_entry() -> None:
    """Verify test execute rejects importance max out of range at entry."""
    cmd = ViewWorkerLogsMCPCommand()
    result = await cmd.execute(importance_max=11)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "importance_max" in result.message
