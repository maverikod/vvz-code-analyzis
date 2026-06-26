"""Unit tests for search_session_schema helpers (T-002/A-001)."""

from __future__ import annotations

from typing import Any

from code_analysis.commands.search_session_schema import (
    OPTIONAL_PAGINATION_PROPERTIES,
    merge_pagination_schema,
)


def _base() -> dict[str, Any]:
    """Return base."""
    return {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "query": {"type": "string"},
        },
        "required": ["project_id", "query"],
        "additionalProperties": False,
    }


def test_merge_preserves_required_keys() -> None:
    """Verify test merge preserves required keys."""
    result = merge_pagination_schema(_base())
    assert "project_id" in result["required"]
    assert "query" in result["required"]


def test_merge_preserves_additionalproperties() -> None:
    """Verify test merge preserves additionalproperties."""
    result = merge_pagination_schema(_base())
    assert result["additionalProperties"] is False


def test_paginated_defaults_to_false() -> None:
    """Verify test paginated defaults to false."""
    result = merge_pagination_schema(_base())
    assert result["properties"]["paginated"]["default"] is False


def test_optional_job_id_and_block_position_present() -> None:
    """Verify test optional job id and block position present."""
    result = merge_pagination_schema(_base())
    props = result["properties"]
    assert "job_id" in props
    assert "block_position" in props
    assert props["block_position"]["minimum"] == 1


def test_pagination_fields_not_in_required() -> None:
    """Verify test pagination fields not in required."""
    result = merge_pagination_schema(_base())
    for field in ("paginated", "include_job_id", "job_id", "block_position"):
        assert field not in result["required"], f"{field} must not be required"


def test_include_job_id_default_false() -> None:
    """Verify test include job id default false."""
    result = merge_pagination_schema(_base(), include_job_id_default=False)
    assert result["properties"]["include_job_id"]["default"] is False


def test_base_schema_not_mutated() -> None:
    """Verify test base schema not mutated."""
    base = _base()
    merge_pagination_schema(base)
    assert "paginated" not in base["properties"]
    assert "job_id" not in base["properties"]


def test_optional_pagination_properties_has_expected_keys() -> None:
    """Verify test optional pagination properties has expected keys."""
    for key in ("paginated", "include_job_id", "job_id", "block_position"):
        assert key in OPTIONAL_PAGINATION_PROPERTIES
