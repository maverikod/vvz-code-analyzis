"""
CST tree finder - find nodes in tree using simple or XPath-like queries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ...cst_query import query_source
from .models import CSTTree, TreeNodeMetadata
from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def find_nodes(
    tree_id: str,
    query: Optional[str] = None,
    search_type: str = "xpath",
    node_type: Optional[str] = None,
    name: Optional[str] = None,
    qualname: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> List[TreeNodeMetadata]:
    """
    Find nodes in tree.

    Supports two search modes:
    1. Simple search: by node_type, name, qualname, line range
    2. XPath-like search: using CSTQuery selector syntax

    Args:
        tree_id: Tree ID
        query: CSTQuery selector string (for xpath search)
        search_type: "simple" or "xpath" (default: "xpath")
        node_type: Node type filter (for simple search)
        name: Node name filter (for simple search)
        qualname: Qualified name filter (for simple search)
        start_line: Start line filter (for simple search)
        end_line: End line filter (for simple search)

    Returns:
        List of TreeNodeMetadata for matching nodes
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    if search_type == "xpath":
        if not query:
            raise ValueError("query parameter required for xpath search")
        return _find_nodes_xpath(tree, query)
    elif search_type == "simple":
        return _find_nodes_simple(tree, node_type, name, qualname, start_line, end_line)
    else:
        raise ValueError(f"Invalid search_type: {search_type}. Must be 'simple' or 'xpath'")


def _find_nodes_xpath(tree: CSTTree, selector: str) -> List[TreeNodeMetadata]:
    """Find nodes using CSTQuery selector."""
    # Get source code from module
    source = tree.module.code

    # Use existing query_source function
    matches = query_source(source, selector, include_code=False)

    # Map matches to node_ids and get metadata
    result: List[TreeNodeMetadata] = []
    for match in matches:
        # Try to find node by matching position
        node_id = match.node_id
        metadata = tree.metadata_map.get(node_id)
        if metadata:
            result.append(metadata)
        else:
            # Try to find by position if node_id doesn't match exactly
            for meta in tree.metadata_map.values():
                if (
                    meta.start_line == match.start_line
                    and meta.start_col == match.start_col
                    and meta.end_line == match.end_line
                    and meta.end_col == match.end_col
                    and meta.type == match.node_type
                ):
                    result.append(meta)
                    break

    return result


def _find_nodes_simple(
    tree: CSTTree,
    node_type: Optional[str] = None,
    name: Optional[str] = None,
    qualname: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> List[TreeNodeMetadata]:
    """Find nodes using simple filters."""
    result: List[TreeNodeMetadata] = []

    for metadata in tree.metadata_map.values():
        # Apply filters
        if node_type and metadata.type != node_type:
            continue
        if name and metadata.name != name:
            continue
        if qualname and metadata.qualname != qualname:
            continue
        if start_line is not None and metadata.start_line < start_line:
            continue
        if end_line is not None and metadata.end_line > end_line:
            continue

        result.append(metadata)

    return result
