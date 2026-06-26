"""Tests for fulltext_search parameter validation."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_mcp_commands_fulltext import FulltextSearchMCPCommand
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import ErrorResult

_VALID_PROJECT_ID = str(uuid.uuid4())


def _mock_project_db() -> MagicMock:
    """Return mock project db."""
    mock_db = MagicMock()
    mock_db.get_project.return_value = {"id": _VALID_PROJECT_ID}
    return mock_db


def _base_params() -> dict[str, object]:
    """Return base params."""
    return {"project_id": _VALID_PROJECT_ID, "query": "database connection"}


def test_validate_params_accepts_limit_in_range() -> None:
    """Verify test validate params accepts limit in range."""
    cmd = FulltextSearchMCPCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_project_db(),
    ):
        out = cmd.validate_params({**_base_params(), "limit": 500})
    assert out["limit"] == 500


@pytest.mark.parametrize("limit", [0, -1, 1001, 5000])
def test_validate_params_rejects_limit_out_of_range(limit: int) -> None:
    """Verify test validate params rejects limit out of range."""
    cmd = FulltextSearchMCPCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_project_db(),
    ):
        with pytest.raises(ValidationError, match="limit") as exc_info:
            cmd.validate_params({**_base_params(), "limit": limit})
    assert exc_info.value.field == "limit"


@pytest.mark.asyncio
async def test_execute_rejects_limit_out_of_range_at_entry() -> None:
    """Verify test execute rejects limit out of range at entry."""
    cmd = FulltextSearchMCPCommand()
    result = await cmd.execute(
        project_id=_VALID_PROJECT_ID,
        query="hello",
        limit=0,
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "limit" in result.message


def test_fulltext_search_validate_params_rejects_unknown_param() -> None:
    """Verify test fulltext search validate params rejects unknown param."""
    cmd = FulltextSearchMCPCommand()
    with pytest.raises(ValidationError, match="unknown parameter"):
        cmd.validate_params({**_base_params(), "__unknown_param__": "x"})


def test_fulltext_search_validate_params_rejects_unknown_project_id() -> None:
    """Verify test fulltext search validate params rejects unknown project id."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    mock_db.get_project.return_value = None
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        with pytest.raises(ValidationError, match="not found"):
            FulltextSearchMCPCommand().validate_params(_base_params())


@pytest.mark.parametrize(
    "entity_type",
    ["invalid_type", "Class", ""],
)
def test_fulltext_search_validate_params_rejects_invalid_entity_type(
    entity_type: str,
) -> None:
    """Verify test fulltext search validate params rejects invalid entity type."""
    cmd = FulltextSearchMCPCommand()
    with pytest.raises(ValidationError, match="entity_type"):
        cmd.validate_params({**_base_params(), "entity_type": entity_type})


@pytest.mark.asyncio
async def test_fulltext_search_execute_rejects_unknown_param() -> None:
    """Verify test fulltext search execute rejects unknown param."""
    cmd = FulltextSearchMCPCommand()
    result = await cmd.execute(
        project_id=_VALID_PROJECT_ID,
        query="hello",
        __unknown_param__="x",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "unknown parameter" in result.message.lower()


@pytest.mark.asyncio
async def test_fulltext_search_execute_rejects_unknown_project_id() -> None:
    """Verify test fulltext search execute rejects unknown project id."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    mock_db.get_project.return_value = None
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        result = await FulltextSearchMCPCommand().execute(
            project_id=_VALID_PROJECT_ID,
            query="hello",
        )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "not found" in result.message.lower()
