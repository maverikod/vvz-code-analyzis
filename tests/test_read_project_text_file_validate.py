"""Tests for read_project_text_file parameter bounds validation."""

from __future__ import annotations

import uuid

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.read_project_text_file_command import (
    ReadProjectTextFileCommand,
)
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> ReadProjectTextFileCommand:
    return ReadProjectTextFileCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    return {
        "project_id": str(uuid.uuid4()),
        "file_path": "README.md",
        "start_line": 1,
        "end_line": 5,
    }


def test_validate_params_accepts_line_range_in_bounds(
    cmd: ReadProjectTextFileCommand,
    base_params: dict[str, object],
) -> None:
    out = cmd.validate_params(dict(base_params))
    assert out["start_line"] == 1
    assert out["end_line"] == 5


@pytest.mark.parametrize("start_line", [0, -1])
def test_validate_params_rejects_start_line_out_of_range(
    cmd: ReadProjectTextFileCommand,
    base_params: dict[str, object],
    start_line: int,
) -> None:
    params = {**base_params, "start_line": start_line}
    with pytest.raises(ValidationError, match="start_line") as exc_info:
        cmd.validate_params(params)
    assert exc_info.value.field == "start_line"


@pytest.mark.asyncio
async def test_execute_rejects_start_line_out_of_range_at_entry(
    cmd: ReadProjectTextFileCommand,
    base_params: dict[str, object],
) -> None:
    result = await cmd.execute(**{**base_params, "start_line": 0})
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "start_line" in result.message
