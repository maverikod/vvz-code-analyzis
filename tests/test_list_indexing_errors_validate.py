"""Tests for list_indexing_errors parameter bounds validation."""

from __future__ import annotations

import pytest

from code_analysis.commands.worker_status_mcp_commands.list_indexing_errors import (
    ListIndexingErrorsMCPCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult


@pytest.fixture
def cmd() -> ListIndexingErrorsMCPCommand:
    """Return cmd."""
    return ListIndexingErrorsMCPCommand()


def test_validate_params_accepts_limit_in_range(
    cmd: ListIndexingErrorsMCPCommand,
) -> None:
    """Verify test validate params accepts limit in range."""
    out = cmd.validate_params({"limit": 500})
    assert out["limit"] == 500


@pytest.mark.parametrize("limit", [0, -1, 1001, 5000])
def test_validate_params_rejects_limit_out_of_range(
    cmd: ListIndexingErrorsMCPCommand,
    limit: int,
) -> None:
    """Verify test validate params rejects limit out of range."""
    with pytest.raises(ValidationError, match="limit") as exc_info:
        cmd.validate_params({"limit": limit})
    assert exc_info.value.field == "limit"


@pytest.mark.asyncio
async def test_execute_rejects_limit_out_of_range_at_entry(
    cmd: ListIndexingErrorsMCPCommand,
) -> None:
    """Verify test execute rejects limit out of range at entry."""
    result = await cmd.execute(limit=0)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "limit" in result.message
