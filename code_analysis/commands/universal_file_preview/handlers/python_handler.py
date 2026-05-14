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

from ..base_handler import FileHandler
from ..errors import (
    PreviewError,
    file_structure_error,
    input_error,
    INPUT_ERROR_UNKNOWN_NODE_REF,
)
from ..models import Node, NodeKind

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
    def open_root(self, file_path: str, session: Any | None) -> Node | PreviewError:
        """
    Parse the Python file and return a tree_node Module root Node.

    When session is None, loads the file via load_file_to_tree to obtain
    stable_ids for all nodes. When session is a CSTTree, uses it directly.
    The root's children are the top-level CST statements, loaded lazily.

    Args:
        file_path: Absolute path to the .py/.pyi/.pyw file.
        session: Existing CSTTree session or None.

    Returns:
        Module root Node (NodeKind.TREE_NODE) or PreviewError.
    """
        try:
            from code_analysis.core.cst_tree.tree_builder import load_file_to_tree

            if session is not None:
                tree = session
            else:
                tree = load_file_to_tree(file_path)

            self._last_file_path = file_path
            self._last_session = tree
            self._last_tree_id = tree.tree_id

            def _load_children() -> list[Node]:
                return _metadata_children_to_nodes(tree, tree.root_node_id)

            return Node(
                node_kind=NodeKind.TREE_NODE,
                node_ref=tree.metadata_map[tree.root_node_id].stable_id if tree.root_node_id else "",
                type_label="Module",
                name=None,
                attributes={},
                _children_loader=_load_children,
            )
        except Exception as exc:
            return file_structure_error(parser="libcst", message=str(exc))

    def resolve_node_ref(
        self, node_ref: str, session: Any | None
    ) -> Node | PreviewError:
        """
        Resolve a stable_id UUID to the CST Node it addresses (C-009).

        Looks up the UUID in the CST node index. Returns UNKNOWN_NODE_REF if
        the UUID is not found.

        Args:
            node_ref: stable_id UUID string from cst_load_file outline_nodes.
            session: CST TreeSession (parsed Module) or None.

        Returns:
            Resolved Node or PreviewError(UNKNOWN_NODE_REF).
        """
        if session is None:
            fp = getattr(self, "_last_file_path", None)
            if fp is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    "No active CST session and no cached file_path to scan.",
                    details={"node_ref": node_ref},
                )
            open_result = self.open_root(fp, None)
            if isinstance(open_result, PreviewError):
                return open_result
            session = getattr(self, "_last_session", None)
            if session is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    "Could not open CST session for stable_id scan.",
                    details={"node_ref": node_ref},
                )

        try:
            from code_analysis.core.cst_tree.tree_metadata import (
                get_node_by_stable_id,
            )

            cst_node = get_node_by_stable_id(session, node_ref)
        except ImportError:
            cst_node = _find_by_stable_id(session, node_ref)

        if cst_node is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"stable_id {node_ref!r} not found in current CST.",
                details={"node_ref": node_ref},
            )
        return _cst_node_to_node(cst_node, node_ref)
def _metadata_children_to_nodes(tree: Any, parent_node_id: str | None) -> list[Node]:
    """Build preview Nodes from CSTTree metadata for direct children of parent_node_id."""
    if parent_node_id is None:
        return []
    # Use outline_nodes: iterate metadata_map and find nodes with parent == parent_node_id
    # that have a meaningful kind (import, class, function, smallstmt)
    _MEANINGFUL_KINDS = frozenset({"import", "class", "function", "method", "smallstmt"})
    _TREE_NODE_KINDS = frozenset({"class", "function", "method"})
    nodes_by_line: list[tuple[int, Any]] = []
    for nid, meta in tree.metadata_map.items():
        if meta.parent_id != parent_node_id:
            continue
        kind = getattr(meta, "kind", "") or ""
        if kind not in _MEANINGFUL_KINDS:
            continue
        nodes_by_line.append((meta.start_line or 0, meta))
    nodes_by_line.sort(key=lambda x: x[0])
    nodes = []
    for _, meta in nodes_by_line:
        node_type = meta.type
        kind_str = getattr(meta, "kind", "") or ""
        preview_kind = NodeKind.TREE_NODE if kind_str in _TREE_NODE_KINDS else NodeKind.SCALAR

        def _make_loader(nid: str) -> Any:
            def _load() -> list[Node]:
                return _metadata_children_to_nodes(tree, nid)
            return _load

        has_children = preview_kind == NodeKind.TREE_NODE
        nodes.append(
            Node(
                node_kind=preview_kind,
                node_ref=meta.stable_id,
                type_label=node_type,
                name=meta.name,
                attributes={},
                _children_loader=_make_loader(meta.node_id) if has_children else None,
            )
        )
    return nodes
def _cst_statements_to_nodes(stmts: Any) -> list[Node]:
    """Convert a sequence of top-level CST statements to preview Nodes lazily."""
    nodes = []
    for stmt in stmts:
        # For SimpleStatementLine, unwrap to get the real inner statement type
        try:
            import libcst as cst
            if isinstance(stmt, cst.SimpleStatementLine) and stmt.body:
                effective_type = type(stmt.body[0]).__name__
                stmt_has_body = False
            else:
                effective_type = type(stmt).__name__
                stmt_has_body = hasattr(stmt, "body")
        except ImportError:
            effective_type = type(stmt).__name__
            stmt_has_body = hasattr(stmt, "body")

        kind = _classify_cst_node(stmt)
        name_attr = getattr(stmt, "name", None)
        name = getattr(name_attr, "value", None)

        def _make_loader(s: Any) -> Any:
            def _load() -> list[Node]:
                body = s.body
                inner = getattr(body, "body", body)
                return _cst_statements_to_nodes(inner)
            return _load

        nodes.append(
            Node(
                node_kind=kind,
                node_ref=getattr(stmt, "_stable_id", "") or "",
                type_label=effective_type,
                name=name,
                attributes={},
                _children_loader=_make_loader(stmt) if stmt_has_body else None,
            )
        )
    return nodes


def _classify_cst_node(node: Any) -> NodeKind:
    """Return NodeKind for a libcst CST node."""
    try:
        import libcst as cst

        if isinstance(node, (cst.ClassDef, cst.FunctionDef, cst.Module)):
            return NodeKind.TREE_NODE
    except ImportError:
        pass
    return NodeKind.SCALAR


def _cst_node_to_node(cst_node: Any, node_ref: str) -> Node:
    """Convert a single libcst CST node to a preview Node."""
    return Node(
        node_kind=_classify_cst_node(cst_node),
        node_ref=node_ref,
        type_label=type(cst_node).__name__,
        name=getattr(getattr(cst_node, "name", None), "value", None),
        attributes={},
    )


def _find_by_stable_id(tree: Any, stable_id: str) -> Any | None:
    """Linear scan of a CST tree for a node with _stable_id == stable_id."""
    import libcst as cst

    class _Finder(cst.CSTVisitor):
        found: Any = None

        def on_visit(self, node: cst.CSTNode) -> bool:
            if getattr(node, "_stable_id", None) == stable_id:
                type(self).found = node
                return False
            return True

    _Finder.found = None
    visitor = _Finder()
    if hasattr(tree, "visit"):
        tree.visit(visitor)
        return visitor.found
    return None
