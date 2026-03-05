"""
Tests for compose_cst_module ops-based interface (Step 05).

Covers selector validation, ops building, and ops-mode execute path.
Integration tests that require project/DB are skipped unless run in E2E.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.cst_compose_module_command import (
    ComposeCSTModuleCommand,
    SUPPORTED_SELECTOR_KINDS,
)
from code_analysis.core.cst_module import ReplaceOp
from mcp_proxy_adapter.commands.result import ErrorResult

# Skip integration tests when project/DB not available (same as test_cst_compose_atomic_integration)
COMPOSE_OPS_SKIP = pytest.mark.skip(
    reason="compose_cst_module ops mode uses RPC driver DB; run in E2E for full flow."
)


# --- Unit tests: _selector_from_dict ---


def test_selector_from_dict_unknown_kind():
    """Unknown selector kind raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported selector kind"):
        ComposeCSTModuleCommand._selector_from_dict({"kind": "unknown"})


def test_selector_from_dict_missing_kind():
    """Missing selector.kind raises ValueError."""
    with pytest.raises(ValueError, match="selector.kind"):
        ComposeCSTModuleCommand._selector_from_dict({"name": "foo"})


def test_selector_from_dict_range_requires_lines():
    """Selector kind 'range' requires start_line and end_line."""
    with pytest.raises(ValueError, match="start_line and end_line"):
        ComposeCSTModuleCommand._selector_from_dict({"kind": "range", "start_line": 1})
    with pytest.raises(ValueError, match="start_line and end_line"):
        ComposeCSTModuleCommand._selector_from_dict({"kind": "range"})


def test_selector_from_dict_block_id_required():
    """Selector kind 'block_id' requires block_id."""
    with pytest.raises(ValueError, match="block_id"):
        ComposeCSTModuleCommand._selector_from_dict({"kind": "block_id"})


def test_selector_from_dict_node_id_required():
    """Selector kind 'node_id' requires node_id."""
    with pytest.raises(ValueError, match="node_id"):
        ComposeCSTModuleCommand._selector_from_dict({"kind": "node_id"})


def test_selector_from_dict_node_id_must_be_uuid4():
    """Selector kind 'node_id' requires valid UUID4 value."""
    with pytest.raises(ValueError, match="UUID4"):
        ComposeCSTModuleCommand._selector_from_dict(
            {"kind": "node_id", "node_id": "not-a-uuid"}
        )
    with pytest.raises(ValueError, match="UUID4"):
        ComposeCSTModuleCommand._selector_from_dict(
            {"kind": "node_id", "node_id": "function:foo:FunctionDef:1:0-10:0"}
        )


def test_selector_from_dict_cst_query_requires_query():
    """Selector kind 'cst_query' requires query."""
    with pytest.raises(ValueError, match="query"):
        ComposeCSTModuleCommand._selector_from_dict({"kind": "cst_query"})


def test_selector_from_dict_cst_query_match_index_non_negative():
    """Selector cst_query match_index must be non-negative integer."""
    with pytest.raises(ValueError, match="match_index"):
        ComposeCSTModuleCommand._selector_from_dict(
            {"kind": "cst_query", "query": "function", "match_index": -1}
        )


def test_selector_from_dict_function_class_method_require_name():
    """Selector kinds function, class, method require name."""
    for kind in ("function", "class", "method"):
        with pytest.raises(ValueError, match="requires name"):
            ComposeCSTModuleCommand._selector_from_dict({"kind": kind})


def test_selector_from_dict_valid_range():
    """Valid range selector builds Selector."""
    sel = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "range", "start_line": 1, "end_line": 10}
    )
    assert sel.kind == "range"
    assert sel.start_line == 1
    assert sel.end_line == 10


def test_selector_from_dict_valid_range_with_span():
    """Valid range selector with start_col/end_col."""
    sel = ComposeCSTModuleCommand._selector_from_dict(
        {
            "kind": "range",
            "start_line": 1,
            "start_col": 0,
            "end_line": 2,
            "end_col": 20,
        }
    )
    assert sel.kind == "range"
    assert sel.start_col == 0
    assert sel.end_col == 20


def test_selector_from_dict_valid_block_id():
    """Valid block_id selector."""
    sel = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "block_id", "block_id": "abc-123"}
    )
    assert sel.kind == "block_id"
    assert sel.block_id == "abc-123"


def test_selector_from_dict_valid_node_id_uuid4():
    """Valid node_id selector (UUID4) builds Selector."""
    uid = "8772a086-688d-4198-a0c4-f03817cc0e6c"
    sel = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "node_id", "node_id": uid}
    )
    assert sel.kind == "node_id"
    assert sel.node_id == uid


def test_selector_from_dict_valid_cst_query():
    """Valid cst_query selector."""
    sel = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "cst_query", "query": "function[name='foo']", "match_index": 0}
    )
    assert sel.kind == "cst_query"
    assert sel.query == "function[name='foo']"
    assert sel.match_index == 0


def test_selector_from_dict_valid_function_class_method():
    """Valid function/class/method selectors."""
    sel_f = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "function", "name": "my_func"}
    )
    assert sel_f.kind == "function" and sel_f.name == "my_func"
    sel_c = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "class", "name": "MyClass"}
    )
    assert sel_c.kind == "class" and sel_c.name == "MyClass"
    sel_m = ComposeCSTModuleCommand._selector_from_dict(
        {"kind": "method", "name": "MyClass.my_method"}
    )
    assert sel_m.kind == "method" and sel_m.name == "MyClass.my_method"


# --- Unit tests: _ops_from_params ---


def test_ops_from_params_empty_raises():
    """Empty ops list raises ValueError."""
    with pytest.raises(ValueError, match="non-empty array"):
        ComposeCSTModuleCommand._ops_from_params([])


def test_ops_from_params_not_list_raises():
    """ops not a list raises ValueError."""
    with pytest.raises(ValueError, match="non-empty array"):
        ComposeCSTModuleCommand._ops_from_params("not a list")


def test_ops_from_params_missing_selector_raises():
    """ops item without selector raises ValueError."""
    with pytest.raises(ValueError, match="selector is required"):
        ComposeCSTModuleCommand._ops_from_params([{"new_code": "x = 1"}])  # no selector


def test_ops_from_params_missing_new_code_raises():
    """ops item without new_code raises ValueError."""
    with pytest.raises(ValueError, match="new_code is required"):
        ComposeCSTModuleCommand._ops_from_params(
            [{"selector": {"kind": "function", "name": "f"}}]  # no new_code
        )


def test_ops_from_params_valid_builds_replace_ops():
    """Valid ops build list of ReplaceOp."""
    ops = ComposeCSTModuleCommand._ops_from_params(
        [
            {
                "selector": {"kind": "function", "name": "foo"},
                "new_code": "def foo(): pass",
            }
        ]
    )
    assert len(ops) == 1
    assert isinstance(ops[0], ReplaceOp)
    assert ops[0].selector.kind == "function"
    assert ops[0].selector.name == "foo"
    assert ops[0].new_code == "def foo(): pass"


def test_ops_from_params_optional_file_docstring():
    """ops item may include file_docstring (e.g. for module kind)."""
    ops = ComposeCSTModuleCommand._ops_from_params(
        [
            {
                "selector": {"kind": "module"},
                "new_code": "def f(): pass",
                "file_docstring": "Module doc.",
            }
        ]
    )
    assert ops[0].file_docstring == "Module doc."


# --- Schema and supported kinds ---


def test_supported_selector_kinds_documented():
    """Supported selector kinds match patcher capabilities."""
    expected = {
        "module",
        "function",
        "class",
        "method",
        "range",
        "block_id",
        "node_id",
        "cst_query",
    }
    assert SUPPORTED_SELECTOR_KINDS == expected


def test_schema_has_ops_and_flags():
    """Command schema includes ops, apply, create_backup, return_diff."""
    schema = ComposeCSTModuleCommand.get_schema()
    assert "ops" in schema["properties"]
    assert "apply" in schema["properties"]
    assert "create_backup" in schema["properties"]
    assert "return_diff" in schema["properties"]
    assert "tree_id" in schema["properties"]
    assert "project_id" in schema["required"]
    assert "file_path" in schema["required"]
    assert "tree_id" not in schema["required"]


# --- Execute validation (no DB) ---


@pytest.mark.asyncio
async def test_execute_requires_either_tree_id_or_ops():
    """Execute returns error when neither tree_id nor ops provided."""
    cmd = ComposeCSTModuleCommand()
    result = await cmd.execute(
        project_id=str(uuid.uuid4()),
        file_path="x.py",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_PARAMS"
    assert "Either tree_id or ops" in result.message


@pytest.mark.asyncio
async def test_execute_accepts_tree_id_with_ops():
    """Execute accepts both tree_id and ops (tree_id used for node_id resolution in ops)."""
    cmd = ComposeCSTModuleCommand()
    result = await cmd.execute(
        project_id=str(uuid.uuid4()),
        file_path="x.py",
        tree_id="some-tree-id",
        ops=[
            {"selector": {"kind": "function", "name": "f"}, "new_code": "def f(): pass"}
        ],
    )
    # With both tree_id and ops we run ops mode; without real project we get project/db error
    assert isinstance(result, ErrorResult)
    assert result.code != "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_execute_ops_returns_error_without_project():
    """Execute with ops without valid project returns error (no success)."""
    cmd = ComposeCSTModuleCommand()
    result = await cmd.execute(
        project_id=str(uuid.uuid4()),
        file_path="x.py",
        ops=[
            {"selector": {"kind": "function", "name": "f"}, "new_code": "def f(): pass"}
        ],
    )
    # Without real project/DB: some error (PROJECT_NOT_FOUND, DATABASE_ERROR, etc.)
    assert isinstance(result, ErrorResult)
