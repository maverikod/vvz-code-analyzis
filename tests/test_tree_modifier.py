"""
Tests for tree_modifier: replace, delete, insert; SimpleStatementLine fix.

Covers: modify_tree replace for module-level import (SimpleStatementLine),
regression for IndentedBlock replace, invalid node_id, parse-invalid replacement.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.core.cst_tree.models import TreeOperation, TreeOperationType
from code_analysis.core.cst_tree.tree_builder import (
    create_tree_from_code,
    get_tree,
    remove_tree,
)
from code_analysis.core.cst_tree.tree_modifier import modify_tree


IMPORT_SOURCE = '''"""Doc."""
from .task_status import TaskStatus

def foo():
    return 1
'''

FUNCTION_BODY_SOURCE = '''"""Doc."""
def bar():
    x = 1
    return x
'''


@pytest.fixture
def tree_with_import(tmp_path):
    """Tree with module-level import (SimpleStatementLine / ImportFrom)."""
    path = str(tmp_path / "sample.py")
    tree = create_tree_from_code(path, IMPORT_SOURCE.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


@pytest.fixture
def tree_with_function(tmp_path):
    """Tree with function and body statements (IndentedBlock)."""
    path = str(tmp_path / "func.py")
    tree = create_tree_from_code(path, FUNCTION_BODY_SOURCE.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


def _find_import_node_id(tree_id: str):
    """Return node_id of the ImportFrom (or first import line) for replace test."""
    t = get_tree(tree_id)
    assert t is not None
    for nid, meta in t.metadata_map.items():
        if meta.type == "ImportFrom" and meta.start_line == 2:
            return nid
    for nid, meta in t.metadata_map.items():
        if meta.type == "SimpleStatementLine" and meta.start_line == 2:
            return nid
    pytest.fail("No import node found in tree")


def _find_function_body_stmt_node_id(tree_id: str):
    """Return node_id of a statement inside the function body (IndentedBlock)."""
    t = get_tree(tree_id)
    assert t is not None
    # "x = 1" is on line 3 in FUNCTION_BODY_SOURCE
    for nid, meta in t.metadata_map.items():
        if meta.type == "SimpleStatementLine" and meta.start_line == 3:
            return nid
    pytest.fail("No body statement found in tree")


class TestReplaceSimpleStatementLineModuleLevel:
    """Replace one SimpleStatementLine (import) in Module.body via cst_modify_tree."""

    def test_replace_import_line_succeeds(self, tree_with_import):
        """Replace module-level import: .task_status -> ..task_status."""
        node_id = _find_import_node_id(tree_with_import)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["from ..task_status import TaskStatus"],
            )
        ]
        modified = modify_tree(tree_with_import, ops)
        code = modified.module.code
        assert "from ..task_status import TaskStatus" in code
        assert "from .task_status import TaskStatus" not in code

    def test_replace_import_line_with_code_string_succeeds(self, tree_with_import):
        """Replace using code= string instead of code_lines."""
        node_id = _find_import_node_id(tree_with_import)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code="from ..task_status import TaskStatus",
            )
        ]
        modified = modify_tree(tree_with_import, ops)
        assert "from ..task_status import TaskStatus" in modified.module.code


class TestReplaceIndentedBlockRegression:
    """Replace statement inside IndentedBlock (no regression)."""

    def test_replace_statement_inside_function_succeeds(self, tree_with_function):
        """Replace statement inside function body (IndentedBlock)."""
        node_id = _find_function_body_stmt_node_id(tree_with_function)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["y = 2"],
            )
        ]
        modified = modify_tree(tree_with_function, ops)
        code = modified.module.code
        assert "y = 2" in code
        assert "x = 1" not in code


class TestReplaceNegative:
    """Invalid node_id and parse-invalid replacement."""

    def test_invalid_node_id_raises(self, tree_with_import):
        """Unknown node_id raises ValueError with stable message."""
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id="nonexistent-node-id",
                code_lines=["from x import y"],
            )
        ]
        with pytest.raises(ValueError) as exc_info:
            modify_tree(tree_with_import, ops)
        msg = str(exc_info.value)
        assert "not found" in msg.lower() or "Node" in msg
        assert "nonexistent" in msg or "first 5" in msg

    def test_parse_invalid_replacement_raises(self, tree_with_import):
        """Syntactically invalid replacement raises ValueError."""
        node_id = _find_import_node_id(tree_with_import)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["from ??? invalid syntax"],
            )
        ]
        with pytest.raises(ValueError) as exc_info:
            modify_tree(tree_with_import, ops)
        msg = str(exc_info.value)
        assert "syntax" in msg.lower() or "parse" in msg.lower() or "Invalid" in msg


def _find_import_from_node_id(tree_id: str) -> str:
    """Return node_id of ImportFrom (child of SimpleStatementLine) to trigger 'was not replaced' when replacing with multiple statements."""
    t = get_tree(tree_id)
    assert t is not None
    for nid, meta in t.metadata_map.items():
        if meta.type == "ImportFrom" and meta.start_line == 2:
            return nid
    pytest.fail("No ImportFrom node found in tree")


def _find_first_two_module_body_node_ids(tree_id: str) -> tuple[str, str]:
    """Return (second_stmt_id, first_stmt_id) so replace_range gets start_idx > end_idx and fails."""
    t = get_tree(tree_id)
    assert t is not None
    root_id = t.root_node_id
    if not root_id:
        pytest.fail("No root node")
    children: list[tuple[int, str]] = []
    for nid, meta in t.metadata_map.items():
        if getattr(meta, "parent_id", None) == root_id:
            start = getattr(meta, "start_line", 0)
            children.append((start, nid))
    children.sort(key=lambda x: x[0])
    if len(children) >= 2:
        return children[1][1], children[0][1]
    pytest.fail("Need at least two module body nodes for replace_range test")


class TestReplaceFailureDiagnostics:
    """Replace failure must include node type, parent type, line range, and fallback hint."""

    def test_replace_failure_includes_diagnostics(self, tree_with_import):
        """When replace fails (e.g. ImportFrom with multiple stmts), message includes type, parent, lines, hint."""
        # Replacing ImportFrom (not in Module.body; SimpleStatementLine is) with multiple statements triggers "was not replaced"
        node_id = _find_import_from_node_id(tree_with_import)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["import a", "import b", "import c"],
            )
        ]
        with pytest.raises(ValueError) as exc_info:
            modify_tree(tree_with_import, ops)
        msg = str(exc_info.value)
        assert "was not replaced" in msg
        assert "Node type:" in msg or "node type" in msg.lower()
        assert "Parent type:" in msg or "parent type" in msg.lower()
        assert "start_line" in msg and "end_line" in msg
        assert "Hint:" in msg or "replace" in msg.lower()

    def test_replace_success_unchanged(self, tree_with_import):
        """Successful replace still returns same success shape (regression)."""
        node_id = _find_import_node_id(tree_with_import)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=node_id,
                code_lines=["from ..task_status import TaskStatus"],
            )
        ]
        modified = modify_tree(tree_with_import, ops)
        assert modified.module is not None
        assert "from ..task_status import TaskStatus" in modified.module.code


class TestReplaceRangeFailureDiagnostics:
    """Replace_range failure must include types, line range, and hint."""

    def test_replace_range_failure_includes_diagnostics(self, tree_with_import):
        """When replace_range fails (start after end in body), message includes types, lines, hint."""
        # Use start_node after end_node in body so range is not replaced (start_idx > end_idx)
        start_id, end_id = _find_first_two_module_body_node_ids(tree_with_import)
        ops = [
            TreeOperation(
                action=TreeOperationType.REPLACE_RANGE,
                start_node_id=start_id,
                end_node_id=end_id,
                code_lines=["x = 1"],
            )
        ]
        with pytest.raises(ValueError) as exc_info:
            modify_tree(tree_with_import, ops)
        msg = str(exc_info.value)
        assert "was not replaced" in msg
        assert "Start node type:" in msg or "node type" in msg.lower()
        assert "Parent type:" in msg or "parent type" in msg.lower()
        assert "line" in msg.lower()
        assert "Hint:" in msg or "consecutive" in msg.lower()
