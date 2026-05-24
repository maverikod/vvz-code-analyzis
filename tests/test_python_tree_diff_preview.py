"""Line-based diff preview for Python edit sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.commands.cst_modify_tree_ops_build import build_tree_operations
from code_analysis.commands.universal_file_edit.sidecar_cst_apply import (
    _normalized_cst_modify_operation,
    _resolve_stable_to_span,
)
from code_analysis.commands.universal_file_preview.budget import PreviewBudget
from code_analysis.commands.universal_file_preview.handlers.python_handler import (
    PythonFileHandler,
)
from code_analysis.commands.universal_file_preview.python_tree_diff_preview import (
    committed_clean_lines,
    render_line_diff_preview,
    render_preview_with_optional_diff,
    session_differs_from_disk,
)
from code_analysis.commands.universal_file_preview.python_visualizer import (
    build_logical_line_to_stable_id,
    clean_logical_lines_for_tree,
    render_annotated_clean_lines,
)
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree, remove_tree
from code_analysis.core.cst_tree.tree_modifier import modify_tree

_CLASS_SRC = """\
class Widget:
    def alpha(self) -> str:
        return "alpha"

    def beta(self) -> str:
        return "beta"

    def gamma(self) -> str:
        return "gamma"
"""


def _apply_replace(tree, *, name: str, code_lines: list[str]):
    meta = next(
        m
        for m in tree.metadata_map.values()
        if m.type == "FunctionDef" and m.name == name
    )
    op = {"type": "replace", "node_id": meta.stable_id, "code_lines": code_lines}
    resolved = _resolve_stable_to_span(op, tree)
    built, err = build_tree_operations(
        tree, [_normalized_cst_modify_operation(resolved)]
    )
    assert err is None and built
    return modify_tree(tree.tree_id, built)


def _apply_delete(tree, *, name: str):
    meta = next(
        m
        for m in tree.metadata_map.values()
        if m.type == "FunctionDef" and m.name == name
    )
    op = {"type": "delete", "node_id": meta.stable_id}
    resolved = _resolve_stable_to_span(op, tree)
    built, err = build_tree_operations(
        tree, [_normalized_cst_modify_operation(resolved)]
    )
    assert err is None and built
    return modify_tree(tree.tree_id, built)


def test_session_differs_from_disk_after_modify(tmp_path) -> None:
    path = tmp_path / "w.py"
    path.write_text(_CLASS_SRC, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    try:
        assert session_differs_from_disk(tree, str(path)) is False
        tree = _apply_replace(
            tree,
            name="alpha",
            code_lines=["def alpha(self) -> str:\n", '    return "alpha-replaced"\n'],
        )
        assert session_differs_from_disk(tree, str(path)) is True
    finally:
        remove_tree(tree.tree_id)


def test_annotated_and_clean_share_line_numbers(tmp_path) -> None:
    path = tmp_path / "w.py"
    path.write_text(_CLASS_SRC, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    try:
        clean = clean_logical_lines_for_tree(tree)
        id_map = build_logical_line_to_stable_id(tree, clean)
        annotated = render_annotated_clean_lines(clean, id_map).splitlines()
        assert len(annotated) == len(clean)
        for ann, raw in zip(annotated, clean):
            assert ann.endswith(raw)
    finally:
        remove_tree(tree.tree_id)


def test_render_line_diff_preview_shows_unified_diff(tmp_path) -> None:
    path = tmp_path / "w.py"
    path.write_text(_CLASS_SRC, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    budget = PreviewBudget(preview_lines=20, value_preview_len=120)
    try:
        tree = _apply_replace(
            tree,
            name="alpha",
            code_lines=["def alpha(self) -> str:\n", '    return "alpha-replaced"\n'],
        )
        text = render_line_diff_preview(
            committed_clean_lines(str(path)),
            clean_logical_lines_for_tree(tree),
            tree,
            budget,
        )
        assert "draft diff" in text
        assert "--- committed" in text
        assert "+++ draft" in text
        assert '- return "alpha"' in text or '-        return "alpha"' in text
        assert "alpha-replaced" in text
    finally:
        remove_tree(tree.tree_id)


def test_python_handler_preview_uses_diff_after_edit(tmp_path) -> None:
    path = tmp_path / "w.py"
    path.write_text(_CLASS_SRC, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=0
    )
    handler = PythonFileHandler()
    try:
        beta_meta = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "beta"
        )
        tree = _apply_delete(tree, name="beta")
        class_meta = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "ClassDef" and m.name == "Widget"
        )
        root = handler.open_root(str(path), tree, budget=budget)
        assert "draft diff" in root.attributes["text"]
        assert "beta" in root.attributes["text"]
        assert (
            f"[{beta_meta.stable_id}]" in root.attributes["text"]
            or "-    def beta" in root.attributes["text"]
        )

        focus = handler.resolve_node_ref(class_meta.stable_id, tree)
        focus_text = focus.attributes["text"]
        assert "draft diff" in focus_text
        assert "beta" in focus_text
        assert "alpha-replaced" not in focus_text
    finally:
        remove_tree(tree.tree_id)


def test_focus_diff_after_unrelated_sibling_edits(tmp_path) -> None:
    """Focus on nested function after class-level edits must not show class hunk."""
    src = (
        "class Widget:\n"
        "    def alpha(self) -> None:\n"
        "        return None\n"
        "\n"
        "    def beta(self) -> int:\n"
        "        return 0\n"
        "\n"
        "def outer() -> None:\n"
        "    def inner_a() -> int:\n"
        "        return 1\n"
        "\n"
        "    def inner_b() -> str:\n"
        '        return "x"\n'
    )
    path = tmp_path / "nested_focus.py"
    path.write_text(src, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    budget = PreviewBudget(preview_lines=30, value_preview_len=120)
    handler = PythonFileHandler()
    try:
        alpha = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "alpha"
        )
        beta = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "beta"
        )
        inner_a = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "inner_a"
        )
        inner_b = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "inner_b"
        )
        outer = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef"
            and m.name == "outer"
            and (m.qualname or "") == "outer"
        )

        for op in (
            {
                "type": "insert",
                "position": "after",
                "target_node_id": alpha.stable_id,
                "code_lines": ["", "def gamma(self) -> bool:", "    return True"],
            },
            {
                "type": "replace",
                "node_id": beta.stable_id,
                "code_lines": ["def beta(self) -> int:", "    return 42"],
            },
        ):
            resolved = _resolve_stable_to_span(op, tree)
            built, err = build_tree_operations(
                tree, [_normalized_cst_modify_operation(resolved)]
            )
            assert err is None and built
            tree = modify_tree(tree.tree_id, built)

        for op in (
            {
                "type": "insert",
                "position": "after",
                "target_node_id": inner_a.stable_id,
                "code_lines": ["", "def inner_mid() -> None:", "    pass"],
            },
            {
                "type": "replace",
                "node_id": inner_b.stable_id,
                "code_lines": ["def inner_b() -> str:", '    return "updated"'],
            },
        ):
            resolved = _resolve_stable_to_span(op, tree)
            built, err = build_tree_operations(
                tree, [_normalized_cst_modify_operation(resolved)]
            )
            assert err is None and built
            tree = modify_tree(tree.tree_id, built)

        focus = handler.resolve_node_ref(outer.stable_id, tree)
        text = focus.attributes["text"]
        assert "draft diff" in text
        assert "def outer" in text
        assert "inner_mid" in text
        assert '"updated"' in text
        assert "def beta" not in text
        assert "return 42" not in text
        assert "def gamma" not in text
    finally:
        remove_tree(tree.tree_id)


def test_render_preview_without_edit_uses_annotated_view(tmp_path) -> None:
    path = tmp_path / "simple.py"
    path.write_text("def foo():\n    return 1\n", encoding="utf-8")
    tree = load_file_to_tree(str(path))
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=50
    )
    try:
        text = render_preview_with_optional_diff(tree, str(path), budget)
        assert "draft diff" not in text
        assert "def foo" in text
    finally:
        remove_tree(tree.tree_id)
