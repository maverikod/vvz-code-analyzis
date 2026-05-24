"""Tests for fs_ggrep pagination schema extension (T-003/A-001)."""
from __future__ import annotations

from code_analysis.commands.fs_ggrep_pagination_schema import (
    document_fs_ggrep_pagination_metadata,
    get_fs_ggrep_schema_with_pagination,
)


def test_schema_includes_optional_pagination_properties() -> None:
    schema = get_fs_ggrep_schema_with_pagination()
    props = schema["properties"]
    assert "paginated" in props
    assert "job_id" in props
    assert "include_job_id" in props
    assert "block_position" in props


def test_paginated_defaults_to_false() -> None:
    schema = get_fs_ggrep_schema_with_pagination()
    assert schema["properties"]["paginated"]["default"] is False


def test_base_required_keys_unchanged() -> None:
    schema = get_fs_ggrep_schema_with_pagination()
    required = set(schema.get("required") or [])
    for field in ("paginated", "job_id", "include_job_id", "block_position"):
        assert field not in required, f"{field} must not be required"


def test_document_metadata_returns_four_keys() -> None:
    meta = document_fs_ggrep_pagination_metadata()
    for key in ("paginated", "job_id", "include_job_id", "block_position"):
        assert key in meta
