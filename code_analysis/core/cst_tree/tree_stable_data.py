"""
Stable data transfer: move stable_id and decorators between tree nodes and external data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import libcst as cst

from .node_stable_id import ensure_stable_id, get_stable_id, set_stable_id

if TYPE_CHECKING:
    from .models import CSTTree


class _StableDataInjector(cst.CSTTransformer):
    """Transformer that ensures every FunctionDef/ClassDef carries its stable_id."""

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.CSTNode:
        """Ensure FunctionDef has stable_id."""
        node, _ = ensure_stable_id(updated_node)
        return node

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.CSTNode:
        """Ensure ClassDef has stable_id."""
        node, _ = ensure_stable_id(updated_node)
        return node


class _StableDataRestorer(cst.CSTTransformer):
    """Transformer that reads stable_id from nodes after mutation and rebuilds index."""

    def __init__(self, stable_map: dict[str, str], decorator_map: dict[str, list]) -> None:
        """Initialize with maps from stable_id to node data."""
        super().__init__()
        self._stable_map = stable_map  # stable_id -> stable_id (identity, for future use)
        self._decorator_map = decorator_map  # stable_id -> decorators list

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.CSTNode:
        """Restore decorators if lost after replace."""
        stable = get_stable_id(updated_node)
        if stable and not updated_node.decorators:
            decs = self._decorator_map.get(stable)
            if decs:
                return updated_node.with_changes(decorators=decs)
        return updated_node

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.CSTNode:
        """Restore decorators if lost after replace."""
        stable = get_stable_id(updated_node)
        if stable and not updated_node.decorators:
            decs = self._decorator_map.get(stable)
            if decs:
                return updated_node.with_changes(decorators=decs)
        return updated_node


def extract_stable_data(tree: CSTTree) -> dict[str, list]:
    """Before mutation: read stable_id->decorators from all nodes into plain data.

    Also ensures every FunctionDef/ClassDef has a stable_id written into it.
    Updates tree.module in-place with injected stable_ids.

    Args:
        tree: CSTTree to extract from

    Returns:
        dict mapping stable_id -> list of cst.Decorator objects
    """
    # Read stable_id -> decorators from metadata_map only (no module modification)
    decorator_map: dict[str, list] = {}
    for nid, meta in tree.metadata_map.items():
        node = tree.node_map.get(nid)
        if node and isinstance(node, (cst.FunctionDef, cst.ClassDef)):
            if meta.stable_id and node.decorators:
                decorator_map[meta.stable_id] = list(node.decorators)
    return decorator_map


def restore_stable_data(tree: CSTTree, decorator_map: dict[str, list]) -> CSTTree:
    """After mutation: restore decorators from data, rebuild index.

    stable_id is already in each unchanged node's leading_lines.
    New nodes (from replace) get a new stable_id via ensure_stable_id.
    Decorators are restored for nodes that lost them during replace.

    Args:
        tree: CSTTree after mutation
        decorator_map: dict mapping stable_id -> decorators (from extract_stable_data)

    Returns:
        Updated CSTTree with restored decorators and rebuilt index
    """
    # Restore decorators for nodes that lost them (no stable_id injection into source)
    new_module = tree.module.visit(_StableDataRestorer({}, decorator_map))
    tree.module = new_module

    # Rebuild full index
    from .tree_builder import _build_tree_index
    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    tree.node_id_aliases.clear()
    _build_tree_index(tree, node_types=None, max_depth=None, include_children=True)

    return tree


def embed_stable_ids_into_tree(tree: "CSTTree") -> None:
    """Write stable_id from metadata_map into each node's leading_lines.

    Must be called after _build_tree_index so that metadata_map is populated.
    After this call, get_stable_id(node) returns the correct stable_id for
    every FunctionDef/ClassDef in tree.module, making nodes self-contained.
    tree.module is replaced in-place with the annotated version.

    Args:
        tree: CSTTree with populated metadata_map and node_map
    """
    # Build node_id -> stable_id lookup from metadata
    nid_to_stable: dict[str, str] = {
        nid: meta.stable_id
        for nid, meta in tree.metadata_map.items()
        if meta.stable_id and meta.type in ("FunctionDef", "ClassDef")
    }
    if not nid_to_stable:
        return

    # Build reverse: node object (by nid) -> stable_id
    # node_map maps nid -> cst node object
    node_to_stable: dict[int, str] = {}
    for nid, stable in nid_to_stable.items():
        node_obj = tree.node_map.get(nid)
        if node_obj is not None:
            node_to_stable[id(node_obj)] = stable

    class _EmbedTransformer(cst.CSTTransformer):
        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.CSTNode:
            stable = node_to_stable.get(id(original_node))
            if stable:
                return set_stable_id(updated_node, stable)
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.CSTNode:
            stable = node_to_stable.get(id(original_node))
            if stable:
                return set_stable_id(updated_node, stable)
            return updated_node

    tree.module = tree.module.visit(_EmbedTransformer())
