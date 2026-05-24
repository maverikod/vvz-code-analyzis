"""Tests for semantic_search parameter validation."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.semantic_search_mcp import SemanticSearchMCPCommand
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult


@pytest.fixture
def cmd() -> SemanticSearchMCPCommand:
    return SemanticSearchMCPCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    return {"project_id": str(uuid.uuid4()), "query": "database connection"}


def test_validate_params_accepts_limit_and_min_score_in_range(
    cmd: SemanticSearchMCPCommand,
    base_params: dict[str, object],
) -> None:
    out = cmd.validate_params({**base_params, "limit": 10, "min_score": 0.5})
    assert out["limit"] == 10
    assert out["min_score"] == 0.5


@pytest.mark.parametrize("limit", [0, -1, 101, 500])
def test_validate_params_rejects_limit_out_of_range(
    cmd: SemanticSearchMCPCommand,
    base_params: dict[str, object],
    limit: int,
) -> None:
    with pytest.raises(ValidationError, match="limit") as exc_info:
        cmd.validate_params({**base_params, "limit": limit})
    assert exc_info.value.field == "limit"


@pytest.mark.parametrize("min_score", [-0.1, -1.0, 1.1, 2.0])
def test_validate_params_rejects_min_score_out_of_range(
    cmd: SemanticSearchMCPCommand,
    base_params: dict[str, object],
    min_score: float,
) -> None:
    with pytest.raises(ValidationError, match="min_score") as exc_info:
        cmd.validate_params({**base_params, "min_score": min_score})
    assert exc_info.value.field == "min_score"


def test_validate_params_rejects_unknown_param(
    cmd: SemanticSearchMCPCommand,
    base_params: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        cmd.validate_params({**base_params, "__unknown_param__": True})


@pytest.mark.asyncio
async def test_execute_rejects_limit_out_of_range_at_entry(
    cmd: SemanticSearchMCPCommand,
    base_params: dict[str, object],
) -> None:
    result = await cmd.execute(
        project_id=str(base_params["project_id"]),
        query=str(base_params["query"]),
        limit=0,
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "limit" in result.message


@pytest.mark.asyncio
async def test_execute_rejects_min_score_out_of_range_at_entry(
    cmd: SemanticSearchMCPCommand,
    base_params: dict[str, object],
) -> None:
    result = await cmd.execute(
        project_id=str(base_params["project_id"]),
        query=str(base_params["query"]),
        min_score=1.5,
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "min_score" in result.message
