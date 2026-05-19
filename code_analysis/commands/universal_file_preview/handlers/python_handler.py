"""
PythonFileHandler — FileHandler for .py, .pyi, .pyw files (C-016).

Opens Python source via the project's cst_load_file infrastructure.
Root NodeKind is tree_node with type label 'Module'.
Identifier format: stable_id UUID from cst_load_file outline_nodes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

import libcst as cst

from ..base_handler import FileHandler
from ..errors import (
    PreviewError,
    input_error,
    INPUT_ERROR_UNKNOWN_NODE_REF,
)
from ..budget import PreviewBudget
from code_analysis.core.cst_tree.node_type_utils import get_decorator_expression

from ..invalid_preview import invalid_source_node
from ..models import Node, NodeKind
from ..python_visualizer import render_module, render_node

logger = logging.getLogger(__name__)


class PythonFileHandler(FileHandler):
    """
    FileHandler for Python files (.py, .pyi, .pyw) (C-016).

    Root NodeKind: tree_node (Module).
    Interior nodes: tree_node for ClassDef and FunctionDef;
    tree_node or scalar for other statements; scalar for leaf values.
    Identifier source: cst_load_file outline_nodes stable_id UUID.
    Lazy materialisation: only root and requested children are loaded.

    Attributes:
        supported_extensions: Frozenset of .py, .pyi, .pyw.
    """

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase extensions this handler supports."""
        return frozenset({".py", ".pyi", ".pyw"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """Parse the Python file, render module overview via PythonNodeRenderer (C-022),
        and return a tree_node Module root Node carrying the rendered text in attributes.

        Args:
            file_path: Absolute path to the .py/.pyi/.pyw file.
            session: Existing CSTTree session or None.
            budget: PreviewBudget for render_module; defaults to (20, 120) when None.

        Returns:
            Module root Node (NodeKind.TREE_NODE) or PreviewError.
        """
        try:
            from code_analysis.core.cst_tree.tree_builder import load_file_to_tree

            tree = session if session is not None else load_file_to_tree(file_path)
            self._last_file_path = file_path
            self._last_session = tree
            self._last_tree_id = getattr(tree, "tree_id", None)
            _budget = (
                budget
                if budget is not None
                else PreviewBudget(preview_lines=20, value_preview_len=120)
            )
            self._last_budget = _budget
            text = render_module(tree, _budget)
            root_stable_id = (
                tree.metadata_map[tree.root_node_id].stable_id
                if tree.root_node_id and tree.root_node_id in tree.metadata_map
                else ""
            )
            return Node(
                node_kind=NodeKind.TREE_NODE,
                node_ref=root_stable_id,
                type_label="Module",
                name=None,
                attributes={"text": text},
                _children_loader=lambda: _cst_preview_child_nodes(
                    tree, tree.root_node_id
                ),
            )
        except Exception as exc:
            return invalid_source_node(file_path, exc)

    def resolve_node_ref(
        self, node_ref: str, session: Any | None
    ) -> Node | PreviewError:
        """Resolve a stable_id UUID to a Node rendered by PythonNodeRenderer (C-009, C-022).

        Args:
            node_ref: stable_id UUID string from cst_load_file outline_nodes.
            session: CSTTree session or None (reopens file if None).

        Returns:
            Resolved Node with rendered text in attributes, or PreviewError.
        """
        if session is None:
            fp = getattr(self, "_last_file_path", None)
            if fp is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    "No active CST session and no cached file_path to scan.",
                    details={"node_ref": node_ref},
                )
            reopen_budget = getattr(self, "_last_budget", None)
            open_result = self.open_root(fp, None, budget=reopen_budget)
            if isinstance(open_result, PreviewError):
                return open_result
            session = getattr(self, "_last_session", None)
            if session is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    "Could not open CST session for stable_id scan.",
                    details={"node_ref": node_ref},
                )

        meta = (
            next(
                (m for m in session.metadata_map.values() if m.stable_id == node_ref),
                None,
            )
            if hasattr(session, "metadata_map")
            else None
        )
        if meta is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"stable_id {node_ref!r} not found in current CST.",
                details={"node_ref": node_ref},
            )
        _budget = getattr(self, "_last_budget", None)
        text = render_node(session, node_ref, _budget)
        parent_cst_id = meta.node_id
        return Node(
            node_kind=NodeKind.TREE_NODE,
            node_ref=node_ref,
            type_label=meta.type,
            name=meta.name,
            attributes={"text": text},
            _children_loader=lambda tree=session, pid=parent_cst_id: (
                _cst_preview_child_nodes(tree, pid)
            ),
        )


def _cst_preview_child_nodes(tree: Any, parent_node_id: str | None) -> list[Node]:
    """Build preview Nodes for CST children visible under a compound node.

    Module-level statements are direct children of the module node. Class and
    function bodies live under ``IndentedBlock`` nodes, so we also collect
    meaningful children of each ``IndentedBlock`` whose parent is
    ``parent_node_id``.
    """
    if parent_node_id is None:
        return []
    _MEANINGFUL_KINDS = frozenset(
        {"import", "class", "function", "method", "smallstmt", "decorator"}
    )
    _TREE_NODE_KINDS = frozenset({"class", "function", "method"})

    def _meaningful_metas_for_parent(pid: str) -> list[Any]:
        acc: list[tuple[int, Any]] = []
        for _nid, meta in tree.metadata_map.items():
            if meta.parent_id != pid:
                continue
            kind = getattr(meta, "kind", "") or ""
            if kind not in _MEANINGFUL_KINDS:
                continue
            acc.append((meta.start_line or 0, meta))
        acc.sort(key=lambda x: x[0])
        return [m for _, m in acc]

    ordered: list[Any] = []
    seen_stable: set[str] = set()
    for meta in _meaningful_metas_for_parent(parent_node_id):
        if meta.stable_id in seen_stable:
            continue
        seen_stable.add(meta.stable_id)
        ordered.append(meta)

    for _nid, meta in tree.metadata_map.items():
        if meta.parent_id != parent_node_id:
            continue
        if meta.type != "IndentedBlock":
            continue
        for inner in _meaningful_metas_for_parent(meta.node_id):
            if inner.stable_id in seen_stable:
                continue
            seen_stable.add(inner.stable_id)
            ordered.append(inner)

    ordered.sort(key=lambda m: m.start_line or 0)

    nodes: list[Node] = []
    for meta in ordered:
        node_type = meta.type
        kind_str = getattr(meta, "kind", "") or ""
        preview_kind = (
            NodeKind.TREE_NODE if kind_str in _TREE_NODE_KINDS else NodeKind.SCALAR
        )

        def _make_loader(nid: str) -> Any:
            def _load() -> list[Node]:
                return _cst_preview_child_nodes(tree, nid)

            return _load

        has_children = preview_kind == NodeKind.TREE_NODE
        attrs: dict[str, Any] = {}
        if kind_str == "decorator" and meta.type == "Decorator":
            cst_node = tree.node_map.get(meta.node_id)
            if isinstance(cst_node, cst.Decorator):
                attrs["expression"] = get_decorator_expression(cst_node)
        nodes.append(
            Node(
                node_kind=preview_kind,
                node_ref=meta.stable_id,
                type_label=node_type,
                name=meta.name,
                attributes=attrs,
                _children_loader=_make_loader(meta.node_id) if has_children else None,
            )
        )
    return nodes
