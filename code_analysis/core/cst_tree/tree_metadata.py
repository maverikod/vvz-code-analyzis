"""
CST tree metadata utilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .models import CSTTree, TreeNodeMetadata
from .tree_builder import get_tree


def get_node_metadata(tree_id: str, node_id: str, include_code: bool = False) -> Optional[TreeNodeMetadata]:
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


def get_node_children(tree_id: str, node_id: str, include_code: bool = False) -> List[TreeNodeMetadata]:
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

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return []

    children: List[TreeNodeMetadata] = []
    for child_id in metadata.children_ids:
        child_metadata = get_node_metadata(tree_id, child_id, include_code=include_code)
        if child_metadata:
            children.append(child_metadata)

    return children


def get_node_parent(tree_id: str, node_id: str) -> Optional[TreeNodeMetadata]:
    """
    Get parent of a node.

    Args:
        tree_id: Tree ID
        node_id: Node ID

    Returns:
        TreeNodeMetadata for parent or None
    """
    tree = get_tree(tree_id)
    if not tree:
        return None

    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None

    if metadata.parent_id:
        return tree.metadata_map.get(metadata.parent_id)

    return None
