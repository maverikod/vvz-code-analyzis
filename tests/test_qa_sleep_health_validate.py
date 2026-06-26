"""Tests for qa_sleep, health, and queue_health parameter validation."""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.core.errors import ValidationError

from code_analysis.commands.health_command import HealthCommand
from code_analysis.commands.qa_sleep_command import QASleepCommand
from code_analysis.commands.queue_health_command import QueueHealthCommand


@pytest.fixture
def qa_sleep_cmd() -> QASleepCommand:
    """Return qa sleep cmd."""
    return QASleepCommand()


def test_qa_sleep_validate_params_accepts_in_range(
    qa_sleep_cmd: QASleepCommand,
) -> None:
    """Verify test qa sleep validate params accepts in range."""
    out = qa_sleep_cmd.validate_params({"seconds": 2.0, "tick_seconds": 0.5})
    assert out["seconds"] == 2.0
    assert out["tick_seconds"] == 0.5


@pytest.mark.parametrize("seconds", [-0.1, -5.0])
def test_qa_sleep_validate_params_rejects_negative_seconds(
    qa_sleep_cmd: QASleepCommand,
    seconds: float,
) -> None:
    """Verify test qa sleep validate params rejects negative seconds."""
    with pytest.raises(ValidationError, match="seconds") as exc_info:
        qa_sleep_cmd.validate_params({"seconds": seconds})
    assert (exc_info.value.data or {}).get("field") == "seconds"


@pytest.mark.parametrize("tick_seconds", [0.0, -0.1, 0.05])
def test_qa_sleep_validate_params_rejects_tick_seconds_below_minimum(
    qa_sleep_cmd: QASleepCommand,
    tick_seconds: float,
) -> None:
    """Verify test qa sleep validate params rejects tick seconds below minimum."""
    with pytest.raises(ValidationError, match="tick_seconds") as exc_info:
        qa_sleep_cmd.validate_params({"tick_seconds": tick_seconds})
    assert (exc_info.value.data or {}).get("field") == "tick_seconds"


def test_qa_sleep_validate_params_rejects_wrong_type_seconds(
    qa_sleep_cmd: QASleepCommand,
) -> None:
    """Verify test qa sleep validate params rejects wrong type seconds."""
    with pytest.raises(ValidationError, match="seconds"):
        qa_sleep_cmd.validate_params({"seconds": "not-a-number"})


def test_qa_sleep_validate_params_rejects_unknown_param(
    qa_sleep_cmd: QASleepCommand,
) -> None:
    """Verify test qa sleep validate params rejects unknown param."""
    with pytest.raises(ValidationError, match="Invalid parameters"):
        qa_sleep_cmd.validate_params({"__unknown_param__": True})


@pytest.mark.asyncio
async def test_qa_sleep_execute_rejects_negative_seconds(
    qa_sleep_cmd: QASleepCommand,
) -> None:
    """Verify test qa sleep execute rejects negative seconds."""
    result = await qa_sleep_cmd.execute(seconds=-1.0)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "seconds" in result.message


@pytest.mark.asyncio
async def test_health_validate_params_rejects_unknown_param() -> None:
    """Verify test health validate params rejects unknown param."""
    cmd = HealthCommand()
    with pytest.raises(ValidationError, match="Invalid parameters"):
        cmd.validate_params({"__unknown_param__": "x"})


@pytest.mark.asyncio
async def test_health_execute_rejects_unknown_param() -> None:
    """Verify test health execute rejects unknown param."""
    result = await HealthCommand().execute(__unknown_param__="x")
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "invalid parameters" in result.message.lower()


@pytest.mark.asyncio
async def test_health_execute_succeeds_with_no_params() -> None:
    """Verify test health execute succeeds with no params."""
    result = await HealthCommand().execute()
    assert isinstance(result, SuccessResult)
    assert "status" in result.data


@pytest.mark.asyncio
async def test_queue_health_validate_params_rejects_unknown_param() -> None:
    """Verify test queue health validate params rejects unknown param."""
    cmd = QueueHealthCommand()
    with pytest.raises(ValidationError, match="Invalid parameters"):
        cmd.validate_params({"__unknown_param__": 1})


@pytest.mark.asyncio
async def test_queue_health_execute_rejects_unknown_param() -> None:
    """Verify test queue health execute rejects unknown param."""
    result = await QueueHealthCommand().execute(__unknown_param__=True)
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "invalid parameters" in result.message.lower()
