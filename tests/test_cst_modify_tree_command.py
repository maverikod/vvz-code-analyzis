"""
Tests for cst_modify_tree MCP command: replace/delete by selector, validation.

Covers: selector-based replace (no prior cst_find_node), node_id backward
compatibility, validation (exactly one of node_id/selector), selector parse error,
selector no match, match_index, replace_all.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.commands.cst_modify_tree_command import CSTModifyTreeCommand
from code_analysis.commands.cst_modify_tree_ops_build import build_tree_operations
from code_analysis.core.cst_tree.tree_builder import (
    create_tree_from_code,
    get_tree,
    remove_tree,
)
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


IMPORT_SOURCE = '''"""Doc."""
from .task_status import TaskStatus

def foo():
    return 1
'''

SOURCE_WITH_CLASS = '''"""Doc."""
from .task_status import TaskStatus

class X:
    def method(self):
        return 0

def foo():
    return 1
'''

# Multiple nodes for batch replace tests (two imports, two functions)
SOURCE_MULTI = '''"""Doc."""
from .a import A
from .b import B

def first():
    return 1

def second():
    return 2
'''

# Three consecutive imports: batch replace (bottom-to-top) forces second lookup
# in modified module; fallback by (start_line, start_col) must pick the correct
# statement, not the neighboring one.
SOURCE_COLLISION_RISK = '''"""Doc."""
from .a import A
from .b import B
from .c import C
'''


@pytest.fixture
def tree_with_import(tmp_path):
    """Tree with module-level import (ImportFrom)."""
    path = str(tmp_path / "sample.py")
    tree = create_tree_from_code(path, IMPORT_SOURCE.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


@pytest.fixture
def tree_with_class(tmp_path):
    """Tree with class and function."""
    path = str(tmp_path / "sample.py")
    tree = create_tree_from_code(path, SOURCE_WITH_CLASS.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


@pytest.fixture
def tree_multi(tmp_path):
    """Tree with two imports and two functions for batch replace tests."""
    path = str(tmp_path / "sample.py")
    tree = create_tree_from_code(path, SOURCE_MULTI.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


@pytest.fixture
def tree_collision_risk(tmp_path):
    """Tree with three consecutive imports for fallback collision-safety test."""
    path = str(tmp_path / "sample.py")
    tree = create_tree_from_code(path, SOURCE_COLLISION_RISK.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


def _find_import_node_id(tree_id: str):
    """Return node_id of the ImportFrom on line 2."""
    t = get_tree(tree_id)
    assert t is not None
    for nid, meta in t.metadata_map.items():
        if meta.type == "ImportFrom" and meta.start_line == 2:
            return nid
    for nid, meta in t.metadata_map.items():
        if meta.type == "SimpleStatementLine" and meta.start_line == 2:
            return nid
    pytest.fail("No import node found in tree")


class TestReplaceBySelector:
    """Replace using selector only (no node_id)."""

    @pytest.mark.asyncio
    async def test_replace_by_selector_import_from_succeeds(self, tree_with_import):
        """Replace ImportFrom using selector only; no prior cst_find_node."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='task_status']",
                    "code_lines": ["from ..task_status import TaskStatus"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..task_status import TaskStatus" in tree.module.code
        assert "from .task_status import TaskStatus" not in tree.module.code

    @pytest.mark.asyncio
    async def test_replace_by_selector_import_from_broad_match_index(
        self, tree_with_import
    ):
        """Replace using broad selector ImportFrom with match_index=0."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom",
                    "match_index": 0,
                    "code_lines": ["from ..task_status import TaskStatus"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..task_status import TaskStatus" in tree.module.code

    @pytest.mark.asyncio
    async def test_replace_by_selector_function_name_foo(self, tree_with_import):
        """Replace function named foo via selector function[name='foo']."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "function[name='foo']",
                    "code_lines": ["def foo():", "    return 2"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "return 2" in tree.module.code
        assert "return 1" not in tree.module.code

    @pytest.mark.asyncio
    async def test_replace_by_selector_class_def(self, tree_with_class):
        """Replace ClassDef named X via selector ClassDef[name='X']."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_class,
            operations=[
                {
                    "action": "replace",
                    "selector": "ClassDef[name='X']",
                    "code_lines": ["class X:", "    pass"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "class X:" in tree.module.code
        assert "def method" not in tree.module.code


class TestReplaceByNodeIdBackwardCompat:
    """Existing replace by node_id still works."""

    @pytest.mark.asyncio
    async def test_replace_by_node_id_succeeds(self, tree_with_import):
        """Replace using node_id only (backward compatibility)."""
        node_id = _find_import_node_id(tree_with_import)
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "node_id": node_id,
                    "code_lines": ["from ..task_status import TaskStatus"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..task_status import TaskStatus" in tree.module.code


class TestValidationReplaceDelete:
    """Validation: exactly one of node_id or selector for replace/delete."""

    @pytest.mark.asyncio
    async def test_replace_both_node_id_and_selector_rejected(self, tree_with_import):
        """Both node_id and selector provided -> reject."""
        node_id = _find_import_node_id(tree_with_import)
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "node_id": node_id,
                    "selector": "ImportFrom",
                    "code_lines": ["from x import y"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_OPERATION"
        assert "exactly one" in result.message or "not both" in result.message

    @pytest.mark.asyncio
    async def test_replace_neither_node_id_nor_selector_rejected(
        self, tree_with_import
    ):
        """Neither node_id nor selector for replace -> reject."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "code_lines": ["from x import y"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_OPERATION"
        assert "node_id or selector" in result.message

    @pytest.mark.asyncio
    async def test_delete_neither_node_id_nor_selector_rejected(self, tree_with_import):
        """Neither node_id nor selector for delete -> reject."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[{"action": "delete"}],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_OPERATION"

    @pytest.mark.asyncio
    async def test_delete_by_selector_succeeds(self, tree_with_import):
        """Delete using selector only."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "delete",
                    "selector": "ImportFrom[module='task_status']",
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from .task_status import TaskStatus" not in tree.module.code
        assert "def foo()" in tree.module.code


class TestInvalidNodeIdRejected:
    """Mutation target IDs must be UUID4; invalid IDs rejected with INVALID_NODE_ID."""

    @pytest.mark.asyncio
    async def test_replace_with_non_uuid4_node_id_returns_invalid_node_id(
        self, tree_with_import
    ):
        """Replace with legacy-style node_id (not UUID4) -> INVALID_NODE_ID."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "node_id": "function:foo:FunctionDef:10:0-20:0",
                    "code_lines": ["def foo():", "    return 2"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_NODE_ID"
        assert "UUID4" in result.message

    @pytest.mark.asyncio
    async def test_replace_with_empty_node_id_returns_invalid_node_id(
        self, tree_with_import
    ):
        """Replace with empty node_id when selector not given -> validation error."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "node_id": "   ",
                    "code_lines": ["x = 1"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_NODE_ID"


class TestSelectorNoMatch:
    """Selector matches no nodes -> explicit error, no tree mutation."""

    @pytest.mark.asyncio
    async def test_selector_no_match_returns_error(self, tree_with_import):
        """Selector that matches nothing -> SELECTOR_NO_MATCH, tree unchanged."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "ClassDef[name='NonExistent']",
                    "code_lines": ["class X: pass"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SELECTOR_NO_MATCH"
        assert "matched no nodes" in result.message or "no nodes" in result.message
        tree = get_tree(tree_with_import)
        assert tree is not None
        assert "from .task_status import TaskStatus" in tree.module.code


class TestSelectorParseError:
    """Invalid selector string -> clear parser/validation error."""

    @pytest.mark.asyncio
    async def test_invalid_selector_returns_parse_error(self, tree_with_import):
        """Invalid selector syntax -> SELECTOR_PARSE_ERROR."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "[unclosed",
                    "code_lines": ["x = 1"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SELECTOR_PARSE_ERROR"
        assert "selector" in result.message.lower() or "Invalid" in result.message


class TestMatchIndex:
    """match_index selects Nth match deterministically."""

    @pytest.mark.asyncio
    async def test_match_index_one_beyond_raises_no_match(self, tree_with_import):
        """match_index=1 when only one ImportFrom -> SELECTOR_NO_MATCH or single match."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom",
                    "match_index": 1,
                    "code_lines": ["from other import Other"],
                }
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SELECTOR_NO_MATCH"


# --- Step 04: batch replace (multi-op, replace_many shorthand, atomicity) ---


class TestBatchReplaceMultiOp:
    """Multiple replace operations in one cst_modify_tree call."""

    @pytest.mark.asyncio
    async def test_multi_replace_in_one_call_applies_all(self, tree_multi):
        """Multiple replace ops with different code; all applied, single persist."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='a']",
                    "code_lines": ["from ..a import A"],
                },
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='b']",
                    "code_lines": ["from ..b import B"],
                },
                {
                    "action": "replace",
                    "selector": "function[name='first']",
                    "code_lines": ["def first():", "    return 10"],
                },
                {
                    "action": "replace",
                    "selector": "function[name='second']",
                    "code_lines": ["def second():", "    return 20"],
                },
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
        assert result.data["operations_applied"] == 4
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        code = tree.module.code
        assert "from ..a import A" in code
        assert "from ..b import B" in code
        assert "return 10" in code
        assert "return 20" in code
        assert "from .a import A" not in code
        lines = code.splitlines()
        assert not any(ln.strip() == "return 1" for ln in lines)
        assert not any(ln.strip() == "return 2" for ln in lines)

    @pytest.mark.asyncio
    async def test_order_safety_deterministic(self, tree_multi):
        """Replace nodes where line shifts are possible; output is deterministic."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom",
                    "match_index": 0,
                    "code_lines": ["from .a import A"],
                },
                {
                    "action": "replace",
                    "selector": "ImportFrom",
                    "match_index": 1,
                    "code_lines": ["from .b import B"],
                },
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 2
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        lines = tree.module.code.splitlines()
        import_lines = [ln for ln in lines if ln.strip().startswith("from ")]
        assert len(import_lines) >= 2
        assert "from .a import A" in tree.module.code
        assert "from .b import B" in tree.module.code


class TestBatchReplaceSelectorMix:
    """Mix selector types in one batch."""

    @pytest.mark.asyncio
    async def test_selector_mix_in_one_batch(self, tree_with_class):
        """Broad type, attribute, nested: each op applies to expected node only."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_class,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom",
                    "match_index": 0,
                    "code_lines": ["from ..task_status import TaskStatus"],
                },
                {
                    "action": "replace",
                    "selector": "function[name='foo']",
                    "code_lines": ["def foo():", "    return 42"],
                },
                {
                    "action": "replace",
                    "selector": "ClassDef[name='X']",
                    "code_lines": ["class X:", "    pass"],
                },
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 3
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..task_status import TaskStatus" in tree.module.code
        assert "return 42" in tree.module.code
        assert "class X:" in tree.module.code
        assert "    pass" in tree.module.code
        assert "def method" not in tree.module.code


class TestBatchReplaceAtomicFailure:
    """One invalid operation in batch -> no partial apply."""

    @pytest.mark.asyncio
    async def test_one_invalid_op_batch_rejected(self, tree_multi):
        """One op with invalid selector syntax -> full batch fails, tree unchanged."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace",
                    "selector": "[unclosed",
                    "code_lines": ["x = 1"],
                },
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='a']",
                    "code_lines": ["from ..a import A"],
                },
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SELECTOR_PARSE_ERROR"
        tree = get_tree(tree_multi)
        assert tree is not None
        assert "from .a import A" in tree.module.code

    @pytest.mark.asyncio
    async def test_one_op_no_matches_batch_rejected(self, tree_multi):
        """One op with no matches -> full batch fails, tree unchanged."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='a']",
                    "code_lines": ["from ..a import A"],
                },
                {
                    "action": "replace",
                    "selector": "ClassDef[name='NonExistent']",
                    "code_lines": ["class X: pass"],
                },
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SELECTOR_NO_MATCH"
        tree = get_tree(tree_multi)
        assert tree is not None
        assert "from .a import A" in tree.module.code

    @pytest.mark.asyncio
    async def test_one_op_out_of_range_match_index_batch_rejected(self, tree_multi):
        """One op with out-of-range match_index -> full batch fails."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='a']",
                    "code_lines": ["from ..a import A"],
                },
                {
                    "action": "replace",
                    "selector": "ImportFrom",
                    "match_index": 99,
                    "code_lines": ["from other import Other"],
                },
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "SELECTOR_NO_MATCH"
        tree = get_tree(tree_multi)
        assert tree is not None
        assert "from .a import A" in tree.module.code


class TestReplaceManyShorthand:
    """replace_many action expanded into multiple replace ops."""

    @pytest.mark.asyncio
    async def test_replace_many_expands_and_applies(self, tree_multi):
        """replace_many with replacements list -> all applied in one call."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace_many",
                    "replacements": [
                        {
                            "selector": "ImportFrom[module='a']",
                            "code_lines": ["from ..a import A"],
                        },
                        {
                            "selector": "function[name='first']",
                            "code_lines": ["def first():", "    return 10"],
                        },
                    ],
                },
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
        assert result.data["operations_applied"] == 2
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..a import A" in tree.module.code
        assert "return 10" in tree.module.code

    @pytest.mark.asyncio
    async def test_replace_many_empty_replacements_rejected(self, tree_multi):
        """replace_many with empty replacements -> INVALID_OPERATION."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[{"action": "replace_many", "replacements": []}],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_OPERATION"
        assert "replacements" in result.message or "non-empty" in result.message

    @pytest.mark.asyncio
    async def test_replace_many_missing_selector_rejected(self, tree_multi):
        """replace_many item without selector -> INVALID_OPERATION."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_multi,
            operations=[
                {
                    "action": "replace_many",
                    "replacements": [{"code_lines": ["x = 1"]}],
                },
            ],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_OPERATION"


class TestBatchRegressionSingleReplace:
    """Regression: single replace (node_id and selector) still works."""

    @pytest.mark.asyncio
    async def test_single_replace_by_selector_unchanged(self, tree_with_import):
        """Single replace with selector (no batch) still works."""
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='task_status']",
                    "code_lines": ["from ..task_status import TaskStatus"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..task_status import TaskStatus" in tree.module.code

    @pytest.mark.asyncio
    async def test_single_replace_by_node_id_unchanged(self, tree_with_import):
        """Single replace with node_id (no batch) still works."""
        node_id = _find_import_node_id(tree_with_import)
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_with_import,
            operations=[
                {
                    "action": "replace",
                    "node_id": node_id,
                    "code_lines": ["from ..task_status import TaskStatus"],
                }
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["operations_applied"] == 1
        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        assert "from ..task_status import TaskStatus" in tree.module.code


class TestFallbackCollisionSafety:
    """
    Collision-safety for start-position fallback in tree_modifier.

    When exact (start_line, start_col, end_line, end_col) does not match after
    a prior replace, the modifier falls back to the statement at (start_line,
    start_col). This test ensures the correct statement is chosen, not a
    neighboring one (e.g. the already-replaced statement).
    """

    @pytest.mark.asyncio
    async def test_batch_replace_fallback_selects_correct_statement(
        self, tree_collision_risk
    ):
        """
        Batch replace of two of three consecutive imports: second op resolves
        in modified module (fallback by start position). Verify only the
        intended statements are replaced and order is preserved.
        """
        cmd = CSTModifyTreeCommand()
        result = await cmd.execute(
            tree_id=tree_collision_risk,
            operations=[
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='a']",
                    "code_lines": ["from ..a import A"],
                },
                {
                    "action": "replace",
                    "selector": "ImportFrom[module='b']",
                    "code_lines": ["from ..b import B"],
                },
            ],
        )
        assert isinstance(result, SuccessResult)
        assert result.data["success"] is True
        assert result.data["operations_applied"] == 2

        tree = get_tree(result.data["tree_id"])
        assert tree is not None
        code = tree.module.code

        # Collect import lines (order preserved) without relying on line numbers
        import_lines = [
            ln.strip() for ln in code.splitlines() if ln.strip().startswith("from ")
        ]
        assert len(import_lines) == 3, (
            "Expected exactly three import lines; wrong count suggests "
            "fallback replaced wrong node or duplicated."
        )

        # Each replacement must land on the correct statement
        assert (
            import_lines[0] == "from ..a import A"
        ), "First line must be replaced .a -> ..a; wrong statement chosen by fallback?"
        assert (
            import_lines[1] == "from ..b import B"
        ), "Second line must be replaced .b -> ..b; wrong statement chosen?"
        assert (
            import_lines[2] == "from .c import C"
        ), "Third line must remain unchanged; fallback must not replace it."

        # No stray old content
        assert "from .a import A" not in code
        assert "from .b import B" not in code


SOURCE_PARAM_AND_NAME = """def foo(a):
    return a + 1
"""

SOURCE_TWO_PARAMS = """def f(a: int, b: int) -> None:
    pass
"""


def _node_id_first_type(tree, node_type: str, *, line: int):
    for nid, meta in tree.metadata_map.items():
        if meta.type == node_type and meta.start_line == line:
            return nid
    pytest.fail(f"No {node_type} on line {line}")


def _param_node_ids_on_line(tree, line: int) -> list[str]:
    """Return Param node_ids on `line` sorted left-to-right."""
    pairs = [
        (nid, meta)
        for nid, meta in tree.metadata_map.items()
        if meta.type == "Param" and meta.start_line == line
    ]
    pairs.sort(key=lambda x: (x[1].start_col, x[1].end_col))
    ids = [nid for nid, _ in pairs]
    if len(ids) < 2:
        pytest.fail(
            f"Expected at least two Param nodes on line {line}, found {len(ids)}"
        )
    return ids


class TestReplaceLeafParamAndName:
    """Replace Param / inner Name without promoting to whole FunctionDef."""

    def test_build_ops_replace_param_keeps_node_id_and_body_unchanged(self, tmp_path):
        path = str(tmp_path / "leaf.py")
        tree = create_tree_from_code(path, SOURCE_PARAM_AND_NAME)
        tree_id = tree.tree_id
        param_id = _node_id_first_type(tree, "Param", line=1)
        ops, err = build_tree_operations(
            tree,
            [
                {
                    "action": "replace",
                    "node_id": param_id,
                    "code_lines": ["b"],
                }
            ],
        )
        assert err is None
        assert len(ops) == 1
        assert ops[0].node_id == param_id
        modify_tree(tree_id, ops)
        out = get_tree(tree_id)
        assert out is not None
        code = out.module.code
        assert "def foo(b):" in code
        assert "return a + 1" in code
        assert "def foo(a):" not in code

    def test_build_ops_replace_name_in_return_keeps_signature(self, tmp_path):
        path = str(tmp_path / "leaf2.py")
        tree = create_tree_from_code(path, SOURCE_PARAM_AND_NAME)
        tree_id = tree.tree_id
        name_id = _node_id_first_type(tree, "Name", line=2)
        ops, err = build_tree_operations(
            tree,
            [
                {
                    "action": "replace",
                    "node_id": name_id,
                    "code_lines": ["x"],
                }
            ],
        )
        assert err is None
        assert ops[0].node_id == name_id
        modify_tree(tree_id, ops)
        out = get_tree(tree_id)
        assert out is not None
        code = out.module.code
        assert "def foo(a):" in code
        assert "return x + 1" in code
        assert "return a + 1" not in code


class TestBatchedTwoParamReplacesEquivalence:
    def test_two_param_replaces_one_modify_matches_sequential(self, tmp_path):
        """Batch two Param replaces equals two sequential modifies."""
        path = str(tmp_path / "seq_two_param.py")
        tree = create_tree_from_code(path, SOURCE_TWO_PARAMS)
        tree_id = tree.tree_id
        ids = _param_node_ids_on_line(tree, line=1)
        assert len(ids) >= 2

        ops, err = build_tree_operations(
            tree,
            [
                {
                    "action": "replace",
                    "node_id": ids[0],
                    "code_lines": ["x: int"],
                }
            ],
        )
        assert err is None
        assert len(ops) == 1
        modify_tree(tree_id, ops)

        tree_mid = get_tree(tree_id)
        assert tree_mid is not None
        ids_mid = _param_node_ids_on_line(tree_mid, line=1)
        ops2, err2 = build_tree_operations(
            tree_mid,
            [
                {
                    "action": "replace",
                    "node_id": ids_mid[1],
                    "code_lines": ["y: int"],
                }
            ],
        )
        assert err2 is None
        modify_tree(tree_id, ops2)

        tree_seq = get_tree(tree_id)
        assert tree_seq is not None
        code_seq = tree_seq.module.code

        path_b = str(tmp_path / "batch_two_param.py")
        tree_b = create_tree_from_code(path_b, SOURCE_TWO_PARAMS)
        tree_id_b = tree_b.tree_id
        ids_b = _param_node_ids_on_line(tree_b, line=1)
        ops_b, err_b = build_tree_operations(
            tree_b,
            [
                {
                    "action": "replace",
                    "node_id": ids_b[0],
                    "code_lines": ["x: int"],
                },
                {
                    "action": "replace",
                    "node_id": ids_b[1],
                    "code_lines": ["y: int"],
                },
            ],
        )
        assert err_b is None
        assert len(ops_b) == 2
        modify_tree(tree_id_b, ops_b)

        tree_batch = get_tree(tree_id_b)
        assert tree_batch is not None
        code_batch = tree_batch.module.code

        assert code_batch == code_seq
