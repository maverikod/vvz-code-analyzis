"""Tests for export_graph parameter bounds validation and metadata alignment."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.ast.graph import ExportGraphMCPCommand
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> ExportGraphMCPCommand:
    return ExportGraphMCPCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    return {"project_id": str(uuid.uuid4())}


def test_validate_params_accepts_limit_in_range(
    cmd: ExportGraphMCPCommand,
    base_params: dict[str, object],
) -> None:
    out = cmd.validate_params({**base_params, "limit": 1000})
    assert out["limit"] == 1000


@pytest.mark.parametrize("limit", [0, -1, 50001, 100000])
def test_validate_params_rejects_limit_out_of_range(
    cmd: ExportGraphMCPCommand,
    base_params: dict[str, object],
    limit: int,
) -> None:
    with pytest.raises(ValidationError, match="limit") as exc_info:
        cmd.validate_params({**base_params, "limit": limit})
    assert exc_info.value.field == "limit"


def test_validate_params_accepts_limit_at_bounds(
    cmd: ExportGraphMCPCommand,
    base_params: dict[str, object],
) -> None:
    out_min = cmd.validate_params({**base_params, "limit": 1})
    out_max = cmd.validate_params({**base_params, "limit": 50000})
    assert out_min["limit"] == 1
    assert out_max["limit"] == 50000


def test_export_graph_schema_and_metadata_limit_aligned() -> None:
    """get_schema() and metadata() must agree on limit bounds and project_id required."""
    schema = ExportGraphMCPCommand.get_schema()
    limit_schema = schema["properties"]["limit"]
    assert limit_schema["default"] == 5000
    assert limit_schema["minimum"] == 1
    assert limit_schema["maximum"] == 50000
    assert "project_id" in schema["required"]

    meta = ExportGraphMCPCommand.metadata()
    limit_meta = meta["parameters"]["limit"]
    assert limit_meta["default"] == 5000
    assert limit_meta["minimum"] == 1
    assert limit_meta["maximum"] == 50000
    assert meta["parameters"]["project_id"]["required"] is True
    assert "root_dir" not in meta["parameters"]
    assert set(meta["parameters"]) == set(schema["properties"])


@pytest.mark.asyncio
async def test_execute_rejects_limit_out_of_range_at_entry(
    cmd: ExportGraphMCPCommand,
    base_params: dict[str, object],
) -> None:
    from mcp_proxy_adapter.commands.result import ErrorResult

    result = await cmd.execute(**{**base_params, "limit": 0})
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "limit" in result.message
