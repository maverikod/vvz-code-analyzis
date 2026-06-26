"""Tests for analyze_timing_bottlenecks parameter bounds validation."""

from __future__ import annotations

import pytest

from code_analysis.commands.log_viewer_mcp_commands.analyze_timing_bottlenecks import (
    AnalyzeTimingBottlenecksMCPCommand,
)
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> AnalyzeTimingBottlenecksMCPCommand:
    """Return cmd."""
    return AnalyzeTimingBottlenecksMCPCommand()


def test_validate_params_accepts_top_n_and_limit_in_range(
    cmd: AnalyzeTimingBottlenecksMCPCommand,
) -> None:
    """Verify test validate params accepts top n and limit in range."""
    out = cmd.validate_params({"top_n": 10, "limit": 50000})
    assert out["top_n"] == 10
    assert out["limit"] == 50000


@pytest.mark.parametrize("top_n", [0, -1, 101, 500])
def test_validate_params_rejects_top_n_out_of_range(
    cmd: AnalyzeTimingBottlenecksMCPCommand,
    top_n: int,
) -> None:
    """Verify test validate params rejects top n out of range."""
    with pytest.raises(ValidationError, match="top_n") as exc_info:
        cmd.validate_params({"top_n": top_n})
    assert exc_info.value.field == "top_n"


@pytest.mark.parametrize("limit", [0, -1, 1_000_001, 2_000_000])
def test_validate_params_rejects_limit_out_of_range(
    cmd: AnalyzeTimingBottlenecksMCPCommand,
    limit: int,
) -> None:
    """Verify test validate params rejects limit out of range."""
    with pytest.raises(ValidationError, match="limit") as exc_info:
        cmd.validate_params({"limit": limit})
    assert exc_info.value.field == "limit"


@pytest.mark.parametrize("tail", [0, -1, -10])
def test_validate_params_rejects_tail_out_of_range(
    cmd: AnalyzeTimingBottlenecksMCPCommand,
    tail: int,
) -> None:
    """Verify test validate params rejects tail out of range."""
    with pytest.raises(ValidationError, match="tail") as exc_info:
        cmd.validate_params({"tail": tail})
    assert exc_info.value.field == "tail"


@pytest.mark.asyncio
async def test_execute_rejects_limit_out_of_range_at_entry(
    cmd: AnalyzeTimingBottlenecksMCPCommand,
) -> None:
    """Verify test execute rejects limit out of range at entry."""
    from mcp_proxy_adapter.commands.result import ErrorResult

    result = await cmd.execute(limit=0)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "limit" in result.message
