"""Tests for project_cross_search parameter validation."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.project_cross_search_command import (
    ProjectCrossSearchCommand,
)
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult


@pytest.fixture
def cmd() -> ProjectCrossSearchCommand:
    """Return cmd."""
    return ProjectCrossSearchCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    """Return base params."""
    return {"project_id": str(uuid.uuid4()), "query": "session guard"}


def test_validate_params_accepts_limit_and_grep_limit_in_range(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test validate params accepts limit and grep limit in range."""
    out = cmd.validate_params({**base_params, "limit": 20, "grep_limit": 200})
    assert out["limit"] == 20
    assert out["grep_limit"] == 200


@pytest.mark.parametrize("limit", [0, -1, 201, 500])
def test_validate_params_rejects_limit_out_of_range(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
    limit: int,
) -> None:
    """Verify test validate params rejects limit out of range."""
    with pytest.raises(ValidationError, match="limit") as exc_info:
        cmd.validate_params({**base_params, "limit": limit})
    assert exc_info.value.field == "limit"


@pytest.mark.parametrize("grep_limit", [-1, 2001, 5000])
def test_validate_params_rejects_grep_limit_out_of_range(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
    grep_limit: int,
) -> None:
    """Verify test validate params rejects grep limit out of range."""
    with pytest.raises(ValidationError, match="grep_limit") as exc_info:
        cmd.validate_params({**base_params, "grep_limit": grep_limit})
    assert exc_info.value.field == "grep_limit"


def test_validate_params_preserves_zero_source_limits(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test validate params preserves zero source limits."""
    out = cmd.validate_params(
        {
            **base_params,
            "semantic_limit": 0,
            "fulltext_limit": 0,
            "grep_limit": 0,
        }
    )
    assert out["semantic_limit"] == 0
    assert out["fulltext_limit"] == 0
    assert out["grep_limit"] == 0


def test_validate_params_rejects_unknown_param(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test validate params rejects unknown param."""
    with pytest.raises(ValidationError):
        cmd.validate_params({**base_params, "__unknown_param__": True})


@pytest.mark.asyncio
async def test_execute_rejects_limit_out_of_range_at_entry(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test execute rejects limit out of range at entry."""
    result = await cmd.execute(
        project_id=str(base_params["project_id"]),
        query=str(base_params["query"]),
        limit=0,
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "limit" in result.message


@pytest.mark.asyncio
async def test_execute_rejects_grep_limit_out_of_range_at_entry(
    cmd: ProjectCrossSearchCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test execute rejects grep limit out of range at entry."""
    result = await cmd.execute(
        project_id=str(base_params["project_id"]),
        query=str(base_params["query"]),
        grep_limit=5000,
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "grep_limit" in result.message
