"""Tests for find_duplicates parameter bounds validation."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.find_duplicates_mcp import FindDuplicatesMCPCommand
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> FindDuplicatesMCPCommand:
    return FindDuplicatesMCPCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    return {"project_id": str(uuid.uuid4())}


def test_validate_params_accepts_thresholds_in_range(
    cmd: FindDuplicatesMCPCommand,
    base_params: dict[str, object],
) -> None:
    with patch.object(BaseMCPCommand, "_validate_project_id_exists", return_value=None):
        out = cmd.validate_params(
            {**base_params, "min_similarity": 0.8, "semantic_threshold": 0.85}
        )
    assert out["min_similarity"] == 0.8
    assert out["semantic_threshold"] == 0.85


@pytest.mark.parametrize("min_similarity", [-0.1, 1.1, 2.0])
def test_validate_params_rejects_min_similarity_out_of_range(
    cmd: FindDuplicatesMCPCommand,
    base_params: dict[str, object],
    min_similarity: float,
) -> None:
    with patch.object(BaseMCPCommand, "_validate_project_id_exists", return_value=None):
        with pytest.raises(ValidationError, match="min_similarity") as exc_info:
            cmd.validate_params({**base_params, "min_similarity": min_similarity})
    assert exc_info.value.field == "min_similarity"


@pytest.mark.parametrize("semantic_threshold", [-0.01, 1.01])
def test_validate_params_rejects_semantic_threshold_out_of_range(
    cmd: FindDuplicatesMCPCommand,
    base_params: dict[str, object],
    semantic_threshold: float,
) -> None:
    with patch.object(BaseMCPCommand, "_validate_project_id_exists", return_value=None):
        with pytest.raises(ValidationError, match="semantic_threshold") as exc_info:
            cmd.validate_params(
                {**base_params, "semantic_threshold": semantic_threshold}
            )
    assert exc_info.value.field == "semantic_threshold"


@pytest.mark.asyncio
async def test_execute_rejects_min_similarity_out_of_range_at_entry(
    cmd: FindDuplicatesMCPCommand,
    base_params: dict[str, object],
) -> None:
    with patch.object(BaseMCPCommand, "_validate_project_id_exists", return_value=None):
        result = await cmd.execute(**{**base_params, "min_similarity": 1.5})
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "min_similarity" in result.message
