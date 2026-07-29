"""
Tests for get_ast bounded pagination and node projection (TODO 1b6cc124).

Covers: flatten_ast_nodes projection/field filtering in isolation, and the
GetASTMCPCommand.execute() paginated-node-listing dispatch (page bounds,
clamping to MAX_LIST_PAGE_SIZE, node_types/fields projection, out-of-range
page, and that omitting all pagination params keeps the legacy whole-tree
``ast`` response unchanged).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.ast.get_ast import GetASTMCPCommand
from code_analysis.commands.ast.get_ast_pagination import (
    ALLOWED_NODE_FIELDS,
    flatten_ast_nodes,
)
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.list_pagination import MAX_LIST_PAGE_SIZE

_SOURCE = (
    "def greet():\n"
    "    return 'hi'\n"
    "\n"
    "\n"
    "class Sample:\n"
    "    def method_one(self):\n"
    "        return 1\n"
    "\n"
    "    def method_two(self):\n"
    "        return 2\n"
)


def test_flatten_ast_nodes_no_filter_includes_every_kind() -> None:
    """Without node_types, every AST node kind is present in the flattened list."""
    tree = ast.parse(_SOURCE)
    nodes = flatten_ast_nodes(tree)
    kinds = {n["node_type"] for n in nodes}
    assert "Module" in kinds
    assert "FunctionDef" in kinds
    assert "ClassDef" in kinds


def test_flatten_ast_nodes_node_types_projection() -> None:
    """node_types restricts output to only the requested AST class names."""
    tree = ast.parse(_SOURCE)
    nodes = flatten_ast_nodes(tree, node_types=["FunctionDef"])
    assert nodes  # greet + method_one + method_two
    assert all(n["node_type"] == "FunctionDef" for n in nodes)
    names = {n.get("name") for n in nodes}
    assert names == {"greet", "method_one", "method_two"}


def test_flatten_ast_nodes_fields_projection_restricts_keys() -> None:
    """fields restricts each node dict to node_type plus the requested fields."""
    tree = ast.parse(_SOURCE)
    nodes = flatten_ast_nodes(
        tree, node_types=["FunctionDef"], fields=["lineno", "name"]
    )
    for node in nodes:
        assert set(node.keys()) <= {"node_type", "lineno", "name"}
        assert "col_offset" not in node


def test_flatten_ast_nodes_fields_ignores_unknown_field_names() -> None:
    """Unknown/unsafe field names are silently dropped, never exposed."""
    tree = ast.parse(_SOURCE)
    nodes = flatten_ast_nodes(
        tree, node_types=["Module"], fields=["__class__", "body", "lineno"]
    )
    for node in nodes:
        assert set(node.keys()) <= {"node_type", "lineno"}


def test_allowed_node_fields_is_a_closed_safe_set() -> None:
    """The allowed field set stays a fixed, non-empty allowlist."""
    assert ALLOWED_NODE_FIELDS
    assert "lineno" in ALLOWED_NODE_FIELDS
    assert "col_offset" in ALLOWED_NODE_FIELDS


def _seed_file(tmp_path: Path, rel: str) -> Path:
    """Write the fixture source under ``tmp_path`` and return its absolute path."""
    target_abs = tmp_path / "proj" / rel
    target_abs.parent.mkdir(parents=True, exist_ok=True)
    target_abs.write_text(_SOURCE, encoding="utf-8")
    return target_abs


def _mock_db_for_indexed_file(target_abs: Path, target_rel: str, file_id: int = 1) -> MagicMock:
    """Build a MagicMock DB whose execute() answers file lookup then searchable-index count."""
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": file_id,
                    "path": str(target_abs.resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
    ]
    mock_db.get_ast.return_value = None
    mock_db.disconnect.return_value = None
    return mock_db


@pytest.mark.asyncio
async def test_get_ast_paginated_node_listing_bounded_page(tmp_path: Path) -> None:
    """page_size/block_position bound the node-listing response."""
    project_root = tmp_path / "proj"
    target_rel = "pkg/mod.py"
    target_abs = _seed_file(tmp_path, target_rel)
    mock_db = _mock_db_for_indexed_file(target_abs, target_rel)

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            node_types=["FunctionDef"],
            page_size=1,
            block_position=1,
        )

    assert isinstance(result, SuccessResult)
    data: Dict[str, Any] = result.data
    assert data["success"] is True
    assert data["paginated"] is True
    assert data["page_size"] == 1
    assert data["block_position"] == 1
    assert data["total"] == 3  # greet + method_one + method_two
    assert data["count"] == 1
    assert data["has_more"] is True
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["node_type"] == "FunctionDef"
    assert "ast" not in data


@pytest.mark.asyncio
async def test_get_ast_paginated_node_listing_page_size_over_max_rejected(
    tmp_path: Path,
) -> None:
    """page_size above MAX_LIST_PAGE_SIZE is rejected by schema validation.

    Same maximum-page-size enforcement convention as list_project_files (the
    ``list_pagination_schema_properties()`` schema declares
    ``maximum: MAX_LIST_PAGE_SIZE`` on ``page_size``, enforced by
    ``BaseMCPCommand.validate_params`` before the command body ever runs).
    """
    project_root = tmp_path / "proj"
    target_rel = "pkg/mod.py"
    target_abs = _seed_file(tmp_path, target_rel)
    mock_db = _mock_db_for_indexed_file(target_abs, target_rel)

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            node_types=["FunctionDef"],
            page_size=MAX_LIST_PAGE_SIZE + 5000,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_ast_paginated_node_listing_page_size_at_max_accepted(
    tmp_path: Path,
) -> None:
    """page_size exactly at MAX_LIST_PAGE_SIZE is accepted (boundary, not off-by-one)."""
    project_root = tmp_path / "proj"
    target_rel = "pkg/mod.py"
    target_abs = _seed_file(tmp_path, target_rel)
    mock_db = _mock_db_for_indexed_file(target_abs, target_rel)

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            node_types=["FunctionDef"],
            page_size=MAX_LIST_PAGE_SIZE,
        )

    assert isinstance(result, SuccessResult)
    assert result.data["page_size"] == MAX_LIST_PAGE_SIZE
    assert result.data["count"] == 3


@pytest.mark.asyncio
async def test_get_ast_paginated_node_listing_out_of_range_page_is_empty(
    tmp_path: Path,
) -> None:
    """A block_position past the last page returns an empty, non-error page."""
    project_root = tmp_path / "proj"
    target_rel = "pkg/mod.py"
    target_abs = _seed_file(tmp_path, target_rel)
    mock_db = _mock_db_for_indexed_file(target_abs, target_rel)

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            node_types=["FunctionDef"],
            page_size=10,
            block_position=99,
        )

    assert isinstance(result, SuccessResult)
    assert result.data["nodes"] == []
    assert result.data["count"] == 0
    assert result.data["total"] == 3
    assert result.data["has_more"] is False


@pytest.mark.asyncio
async def test_get_ast_paginated_node_listing_field_projection(tmp_path: Path) -> None:
    """fields restricts each returned node to the requested field subset."""
    project_root = tmp_path / "proj"
    target_rel = "pkg/mod.py"
    target_abs = _seed_file(tmp_path, target_rel)
    mock_db = _mock_db_for_indexed_file(target_abs, target_rel)

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            node_types=["FunctionDef"],
            fields=["lineno"],
            page_size=10,
        )

    assert isinstance(result, SuccessResult)
    for node in result.data["nodes"]:
        assert set(node.keys()) <= {"node_type", "lineno"}


@pytest.mark.asyncio
async def test_get_ast_without_pagination_params_keeps_whole_tree_response(
    tmp_path: Path,
) -> None:
    """Omitting every pagination/projection param keeps the legacy whole-tree response."""
    project_root = tmp_path / "proj"
    target_rel = "pkg/mod.py"
    target_abs = _seed_file(tmp_path, target_rel)
    mock_db = _mock_db_for_indexed_file(target_abs, target_rel)

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(project_id="p1", file_path=target_rel)

    assert isinstance(result, SuccessResult)
    assert "paginated" not in result.data
    assert "nodes" not in result.data
    assert isinstance(result.data["ast"], str)  # legacy ast.dump() string


@pytest.mark.asyncio
async def test_get_ast_paginated_node_listing_missing_disk_file_errors(
    tmp_path: Path,
) -> None:
    """Pagination mode against a file resolvable in DB but absent on disk errors cleanly."""
    project_root = tmp_path / "proj"
    target_rel = "pkg/gone.py"
    mock_db = MagicMock()
    mock_db.execute.side_effect = [
        {
            "data": [
                {
                    "id": 7,
                    "path": str((project_root / target_rel).resolve()),
                    "relative_path": target_rel,
                    "deleted": 0,
                }
            ]
        },
        {"data": [{"classes_count": 1, "functions_count": 0, "methods_count": 0}]},
    ]
    mock_db.get_ast.return_value = None
    mock_db.disconnect.return_value = None

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=mock_db),
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=project_root),
    ):
        cmd = GetASTMCPCommand()
        result = await cmd.execute(
            project_id="p1",
            file_path=target_rel,
            page_size=10,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "FILE_NOT_FOUND"
