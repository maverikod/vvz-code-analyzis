"""Tests for G-008 backward-compatible pagination schema helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from code_analysis.commands.fs_ggrep_pagination_schema import (
    document_fs_ggrep_pagination_metadata,
    get_fs_ggrep_schema_with_pagination,
)
from code_analysis.commands.search_mcp_commands_fulltext import FulltextSearchMCPCommand
from code_analysis.commands.search_session_schema import (
    OPTIONAL_PAGINATION_PROPERTIES,
    merge_pagination_schema,
)
from code_analysis.commands.semantic_search_pagination_schema import (
    document_semantic_search_pagination_metadata,
    get_semantic_search_schema_with_pagination,
)

INVENTORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/plans/2026-05-21-paginated-search-results/existing_behavior_inventory.yaml"
)

PAGINATION_KEYS = frozenset(
    {"paginated", "include_job_id", "job_id", "block_position"},
)


def test_merge_pagination_schema_preserves_base_required_keys() -> None:
    """Verify test merge pagination schema preserves base required keys."""
    base = {
        "type": "object",
        "properties": {"project_id": {"type": "string"}, "query": {"type": "string"}},
        "required": ["project_id", "query"],
        "additionalProperties": False,
    }
    merged = merge_pagination_schema(base)
    assert merged["required"] == ["project_id", "query"]
    assert set(merged["properties"]) >= {"project_id", "query"} | PAGINATION_KEYS


def test_merge_pagination_schema_paginated_defaults_false() -> None:
    """Verify test merge pagination schema paginated defaults false."""
    assert OPTIONAL_PAGINATION_PROPERTIES["paginated"]["default"] is False
    merged = merge_pagination_schema({"type": "object", "properties": {}})
    assert merged["properties"]["paginated"]["default"] is False


def test_merge_pagination_schema_include_job_id_default_override() -> None:
    """Verify test merge pagination schema include job id default override."""
    merged = merge_pagination_schema(
        {"type": "object", "properties": {}},
        include_job_id_default=False,
    )
    assert merged["properties"]["include_job_id"]["default"] is False


def test_fs_ggrep_schema_with_pagination() -> None:
    """Verify test fs ggrep schema with pagination."""
    schema = get_fs_ggrep_schema_with_pagination()
    props = schema.get("properties") or {}
    assert PAGINATION_KEYS <= set(props)
    assert schema.get("required")
    assert "paginated" in document_fs_ggrep_pagination_metadata()


def test_semantic_search_schema_with_pagination() -> None:
    """Verify test semantic search schema with pagination."""
    schema = get_semantic_search_schema_with_pagination()
    props = schema.get("properties") or {}
    assert PAGINATION_KEYS <= set(props)
    assert set(schema.get("required") or []) == {"project_id", "query"}
    assert "paginated" in document_semantic_search_pagination_metadata()


def test_fulltext_search_schema_includes_optional_pagination() -> None:
    """Verify test fulltext search schema includes optional pagination."""
    schema = FulltextSearchMCPCommand.get_schema()
    props = schema.get("properties") or {}
    assert PAGINATION_KEYS <= set(props)
    assert set(schema.get("required") or []) == {"project_id", "query"}
    assert props["paginated"]["default"] is False


def test_fulltext_search_metadata_documents_pagination() -> None:
    """Verify test fulltext search metadata documents pagination."""
    meta = FulltextSearchMCPCommand.metadata()
    params = meta.get("parameters") or {}
    assert PAGINATION_KEYS <= set(params)
    best = meta.get("best_practices") or []
    assert any("paginated defaults to false" in item.lower() for item in best)


def test_existing_behavior_inventory_covers_plan_commands() -> None:
    """Verify test existing behavior inventory covers plan commands."""
    assert INVENTORY_PATH.is_file()
    data = yaml.safe_load(INVENTORY_PATH.read_text(encoding="utf-8"))
    command_names = {entry["name"] for entry in data["commands"]}
    assert command_names == {
        "fs_grep",
        "fulltext_search",
        "semantic_search",
        "project_cross_search",
        "search_start",
        "search_get_page",
        "search_get_status",
        "search_cancel",
        "search_close",
    }
    for entry in data["commands"]:
        assert "existing" in entry and "new" in entry
        assert isinstance(entry["existing"], list)
        assert isinstance(entry["new"], list)
    assert data["meta"]["plan"] == "paginated-search-results"
    assert "search_session package" in data["infrastructure"]["new"]
