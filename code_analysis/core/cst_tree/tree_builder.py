"""
CST tree builder - loads file into CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Set

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .models import CSTTree, TreeNodeMetadata

logger = logging.getLogger(__name__)

# In-memory storage for CST trees
_trees: dict[str, CSTTree] = {}


def load_file_to_tree(
    file_path: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> CSTTree:
    """
    Load file into CST tree and store in memory.

    Args:
        file_path: Path to Python file
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        CSTTree with tree_id and metadata
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix != ".py":
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    # Read and parse file
    source = path.read_text(encoding="utf-8")
    module = cst.parse_module(source)

    # Create tree
    tree = CSTTree.create(str(path.resolve()), module)

    # Build node index and metadata
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
    )

    # Store in memory
    _trees[tree.tree_id] = tree

    return tree


def _build_tree_index(
    tree: CSTTree,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> None:
    """
    Build node index and metadata for tree.

    Args:
        tree: CSTTree to build index for
        node_types: Optional filter by node types
        max_depth: Optional maximum depth
        include_children: Whether to include children information
    """
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    node_types_set: Optional[Set[str]] = None
    if node_types:
        node_types_set = {t.lower() for t in node_types}

    class_stack: List[str] = []
    func_stack: List[str] = []

    def visit(node: cst.CSTNode, depth: int) -> None:
        # Check depth filter
        if max_depth is not None and depth > max_depth:
            return

        # Check node type filter
        node_type = node.__class__.__name__
        if node_types_set and node_type.lower() not in node_types_set:
            # Still visit children even if this node doesn't match
            for child in node.children:
                visit(child, depth + 1)
            return

        # Get position
        pos = positions.get(node)
        if pos is None:
            return

        try:
            start_line = (
                pos.start.line
                if hasattr(pos, "start") and hasattr(pos.start, "line")
                else 1
            )
            start_col = (
                pos.start.column
                if hasattr(pos, "start") and hasattr(pos.start, "column")
                else 0
            )
            end_line = (
                pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
            )
            end_col = (
                pos.end.column
                if hasattr(pos, "end") and hasattr(pos.end, "column")
                else 0
            )
        except (AttributeError, TypeError):
            return

        # Get parent
        parent = parents.get(node)

        # Generate node_id
        node_id = _generate_node_id(
            node, start_line, start_col, end_line, end_col, class_stack, func_stack
        )

        # Store node
        tree.node_map[node_id] = node
        if parent:
            parent_id = _get_node_id_for_node(
                parent, positions, class_stack, func_stack
            )
            tree.parent_map[node_id] = parent_id
        else:
            tree.parent_map[node_id] = None

        # Get name and qualname
        name = _get_node_name(node)
        qualname = _get_node_qualname(node, class_stack, func_stack)

        # Get kind
        kind = _get_node_kind(node, class_stack)

        # Get children
        children_ids: List[str] = []
        if include_children:
            for child in node.children:
                child_pos = positions.get(child)
                if child_pos:
                    try:
                        child_start_line = (
                            child_pos.start.line
                            if hasattr(child_pos, "start")
                            and hasattr(child_pos.start, "line")
                            else 1
                        )
                        child_start_col = (
                            child_pos.start.column
                            if hasattr(child_pos, "start")
                            and hasattr(child_pos.start, "column")
                            else 0
                        )
                        child_end_line = (
                            child_pos.end.line
                            if hasattr(child_pos, "end")
                            and hasattr(child_pos.end, "line")
                            else 1
                        )
                        child_end_col = (
                            child_pos.end.column
                            if hasattr(child_pos, "end")
                            and hasattr(child_pos.end, "column")
                            else 0
                        )
                        child_id = _generate_node_id(
                            child,
                            child_start_line,
                            child_start_col,
                            child_end_line,
                            child_end_col,
                            class_stack,
                            func_stack,
                        )
                        children_ids.append(child_id)
                    except (AttributeError, TypeError):
                        pass

        # Create metadata
        metadata = TreeNodeMetadata(
            node_id=node_id,
            type=node_type,
            kind=kind,
            name=name,
            qualname=qualname,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            children_count=len(children_ids),
            children_ids=children_ids if include_children else [],
            parent_id=tree.parent_map.get(node_id),
        )

        tree.metadata_map[node_id] = metadata

        # Track class/function stacks
        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        # Visit children
        for child in node.children:
            visit(child, depth + 1)

        # Pop stacks
        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(tree.module, 0)


def _generate_node_id(
    node: cst.CSTNode,
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
    class_stack: List[str],
    func_stack: List[str],
) -> str:
    """Generate stable node ID."""
    node_type = node.__class__.__name__
    kind = _get_node_kind(node, class_stack)
    qualname = _get_node_qualname(node, class_stack, func_stack) or ""
    return (
        f"{kind}:{qualname}:{node_type}:{start_line}:{start_col}-{end_line}:{end_col}"
    )


def _get_node_id_for_node(
    node: cst.CSTNode,
    positions: dict,
    class_stack: List[str],
    func_stack: List[str],
) -> Optional[str]:
    """Get node_id for a node (used for parent lookup)."""
    pos = positions.get(node)
    if pos is None:
        return None
    try:
        start_line = (
            pos.start.line
            if hasattr(pos, "start") and hasattr(pos.start, "line")
            else 1
        )
        start_col = (
            pos.start.column
            if hasattr(pos, "start") and hasattr(pos.start, "column")
            else 0
        )
        end_line = (
            pos.end.line if hasattr(pos, "end") and hasattr(pos.end, "line") else 1
        )
        end_col = (
            pos.end.column if hasattr(pos, "end") and hasattr(pos.end, "column") else 0
        )
        return _generate_node_id(
            node, start_line, start_col, end_line, end_col, class_stack, func_stack
        )
    except (AttributeError, TypeError):
        return None


def _get_node_name(node: cst.CSTNode) -> Optional[str]:
    """Get node name."""
    if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
        return node.name.value
    if isinstance(node, cst.Name):
        return node.value
    return None


def _get_node_kind(node: cst.CSTNode, class_stack: List[str]) -> str:
    """Get node kind."""
    if isinstance(node, cst.ClassDef):
        return "class"
    if isinstance(node, cst.FunctionDef):
        return "method" if class_stack else "function"
    if isinstance(node, (cst.Import, cst.ImportFrom)):
        return "import"
    if isinstance(node, cst.BaseSmallStatement):
        return "smallstmt"
    if isinstance(node, cst.BaseStatement):
        return "stmt"
    return "node"


def _get_node_qualname(
    node: cst.CSTNode, class_stack: List[str], func_stack: List[str]
) -> Optional[str]:
    """Get qualified name for node."""
    if isinstance(node, cst.ClassDef):
        return (
            ".".join(class_stack + [node.name.value])
            if class_stack
            else node.name.value
        )
    if isinstance(node, cst.FunctionDef):
        if class_stack:
            return ".".join(class_stack + [node.name.value])
        parts = list(func_stack[:-1]) + [node.name.value]
        return ".".join(parts) if parts else node.name.value
    return ".".join(class_stack + func_stack) if (class_stack or func_stack) else None


def get_tree(tree_id: str) -> Optional[CSTTree]:
    """Get tree by tree_id."""
    return _trees.get(tree_id)


def remove_tree(tree_id: str) -> bool:
    """Remove tree from memory."""
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False


def reload_tree_from_file(
    tree_id: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> Optional[CSTTree]:
    """
    Reload tree from file, updating existing tree in memory.

    This function updates an existing tree by reloading it from the file on disk.
    The tree_id remains the same, so all references to the tree remain valid.

    Args:
        tree_id: Existing tree ID to update
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        Updated CSTTree or None if tree not found

    Raises:
        FileNotFoundError: If file not found
        ValueError: If file is not a Python file
    """
    tree = get_tree(tree_id)
    if not tree:
        return None

    # Read and parse file
    path = Path(tree.file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {tree.file_path}")
    if path.suffix != ".py":
        raise ValueError(f"File must be a Python file (.py): {tree.file_path}")

    source = path.read_text(encoding="utf-8")
    module = cst.parse_module(source)

    # Update tree in place
    tree.module = module
    tree.file_path = str(path.resolve())

    # Rebuild index
    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
    )

    return tree
