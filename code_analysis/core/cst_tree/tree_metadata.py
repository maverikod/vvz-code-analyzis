"""
CST tree metadata utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .models import CSTTree, ROOT_NODE_ID_SENTINEL, TreeNodeMetadata
from .tree_builder import get_tree


def _resolve_node_id(tree: Optional[CSTTree], node_id: str) -> str:
    """Resolve reserved __root__ to the tree's root node_id."""
    if node_id == ROOT_NODE_ID_SENTINEL and tree and tree.root_node_id:
        return tree.root_node_id
    return node_id


def get_node_metadata(
    tree_id: str, node_id: str, include_code: bool = False
) -> Optional[TreeNodeMetadata]:
    """
    Get metadata for a node.

    Args:
        tree_id: Tree ID
        node_id: Node ID
        include_code: Whether to include code snippet

    Returns:
        TreeNodeMetadata or None if not found
    """
    tree = get_tree(tree_id)
    if not tree:
        return None
    node_id = _resolve_node_id(tree, node_id)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None

    if include_code:
        node = tree.node_map.get(node_id)
        if node:
            code = tree.module.code_for_node(node)
            # Create new metadata with code
            return TreeNodeMetadata(
                node_id=metadata.node_id,
                type=metadata.type,
                kind=metadata.kind,
                name=metadata.name,
                qualname=metadata.qualname,
                start_line=metadata.start_line,
                start_col=metadata.start_col,
                end_line=metadata.end_line,
                end_col=metadata.end_col,
                children_count=metadata.children_count,
                children_ids=metadata.children_ids,
                parent_id=metadata.parent_id,
                code=code,
            )

    return metadata


def get_node_children(
    tree_id: str, node_id: str, include_code: bool = False
) -> List[TreeNodeMetadata]:
    """
    Get children of a node.

    Args:
        tree_id: Tree ID
        node_id: Node ID
        include_code: Whether to include code snippets

    Returns:
        List of TreeNodeMetadata for children
    """
    tree = get_tree(tree_id)
    if not tree:
        return []
    node_id = _resolve_node_id(tree, node_id)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return []

    children: List[TreeNodeMetadata] = []
    for child_id in metadata.children_ids:
        child_metadata = get_node_metadata(tree_id, child_id, include_code=include_code)
        if child_metadata:
            children.append(child_metadata)

    return children


def get_node_descendants(
    tree_id: str,
    node_id: str,
    max_depth: int = 1,
    include_code: bool = False,
) -> List[Tuple[TreeNodeMetadata, int]]:
    """
    Get descendants of a node up to max_depth levels (flat list with depth).

    Args:
        tree_id: Tree ID
        node_id: Node ID
        max_depth: 1 = direct children only, 2 = children + grandchildren, etc.
                   <= 0 means no limit (full subtree).
        include_code: Whether to include code snippets in metadata

    Returns:
        Flat list of (TreeNodeMetadata, depth). depth 1 = direct child, 2 = grandchild.
    """
    tree = get_tree(tree_id)
    if not tree:
        return []
    node_id = _resolve_node_id(tree, node_id)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return []

    result: List[Tuple[TreeNodeMetadata, int]] = []
    frontier: List[Tuple[str, int]] = [(cid, 1) for cid in metadata.children_ids]
    while frontier:
        nid, depth = frontier.pop(0)
        if max_depth > 0 and depth > max_depth:
            continue
        child_meta = get_node_metadata(tree_id, nid, include_code=include_code)
        if child_meta:
            result.append((child_meta, depth))
            if max_depth <= 0 or depth < max_depth:
                for cid in child_meta.children_ids:
                    frontier.append((cid, depth + 1))
    return result


def get_node_parent(tree_id: str, node_id: str) -> Optional[TreeNodeMetadata]:
    """
    Get parent of a node.

    Args:
        tree_id: Tree ID
        node_id: Node ID (or __root__ for Module; root has no parent)

    Returns:
        TreeNodeMetadata for parent or None
    """
    tree = get_tree(tree_id)
    if not tree:
        return None
    node_id = _resolve_node_id(tree, node_id)

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None

    if metadata.parent_id:
        return tree.metadata_map.get(metadata.parent_id)

    return None
