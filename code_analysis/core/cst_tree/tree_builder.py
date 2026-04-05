"""
CST tree builder - loads file into CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider, PositionProvider

from .models import CSTTree, TreeNodeMetadata
from .node_id_markers import (
    PersistedNodeIds,
    build_marker_path,
    build_exact_key_to_id_from_metadata,
    build_exact_node_key,
    strip_persisted_node_ids,
)
from .node_type_utils import get_node_kind, get_node_name, get_node_qualname

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
    is_py = path.suffix == ".py"
    is_py_tmp = path.suffix == ".tmp" and path.stem.endswith(".py")
    if not is_py and not is_py_tmp:
        raise ValueError(f"File must be a Python file (.py): {file_path}")

    source = path.read_text(encoding="utf-8")
    logical_source, persisted_node_ids = strip_persisted_node_ids(source)
    module = cst.parse_module(logical_source)
    tree = CSTTree.create(str(path.resolve()), module)
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        persisted_node_ids=persisted_node_ids,
    )

    _trees[tree.tree_id] = tree
    return tree


def create_tree_from_code(
    file_path: str,
    source_code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> CSTTree:
    """
    Create CST tree from source code string (without reading from file).

    This is useful for creating trees from code that doesn't exist on disk yet.

    Args:
        file_path: Path where file will be saved (used for tree metadata)
        source_code: Python source code string
        node_types: Optional filter by node types (e.g., ["FunctionDef", "ClassDef"])
        max_depth: Optional maximum depth for node filtering
        include_children: Whether to include children information in metadata

    Returns:
        CSTTree with tree_id and metadata
    """
    logical_source, persisted_node_ids = strip_persisted_node_ids(source_code)
    module = cst.parse_module(logical_source)

    tree = CSTTree.create(str(Path(file_path).resolve()), module)
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        persisted_node_ids=persisted_node_ids,
    )

    _trees[tree.tree_id] = tree
    return tree


def _build_tree_index(
    tree: CSTTree,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
    previous_metadata_map: Optional[Dict[str, TreeNodeMetadata]] = None,
    replaced_positions_to_id: Optional[Dict[Tuple[int, int, str], str]] = None,
    persisted_node_ids: Optional[PersistedNodeIds] = None,
) -> None:
    """
    Build node index and metadata for tree.

    When previous_metadata_map and optionally replaced_positions_to_id are
    provided (e.g. after modify_tree), node_ids are preserved: unchanged nodes
    keep their id by exact (start_line, start_col, end_line, end_col, type);
    the node that replaced content at (start_line, start_col) gets the old id.

    Args:
        tree: CSTTree to build index for
        node_types: Optional filter by node types
        max_depth: Optional maximum depth
        include_children: Whether to include children information
        previous_metadata_map: Optional snapshot of metadata before modify (for id preservation)
        replaced_positions_to_id: Optional (start_line, start_col) -> node_id for replaced nodes
    """
    wrapper = MetadataWrapper(tree.module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)

    node_types_set: Optional[Set[str]] = None
    if node_types:
        node_types_set = {t.lower() for t in node_types}

    # Build (start_line, start_col, end_line, end_col, type) -> node_id for id preservation
    exact_key_to_id: Dict[Tuple[int, int, int, int, str], str] = {}
    if persisted_node_ids:
        exact_key_to_id.update(persisted_node_ids)
    if previous_metadata_map:
        for key, node_id in build_exact_key_to_id_from_metadata(
            previous_metadata_map
        ).items():
            exact_key_to_id.setdefault(key, node_id)
    # Mutable copy so we pop when we assign (each replaced id used at most once)
    replaced_map: Dict[Tuple[int, int, str], str] = {}
    if replaced_positions_to_id:
        replaced_map = dict(replaced_positions_to_id)

    class_stack: List[str] = []
    func_stack: List[str] = []
    # Map node object id -> node_id (UUID4) so parent/children resolve after visit
    node_to_uuid: Dict[int, str] = {}

    def visit(node: cst.CSTNode, depth: int, path_indices: tuple[int, ...]) -> None:
        # Check depth filter
        if max_depth is not None and depth > max_depth:
            return

        # Check node type filter (always index root so __root__ resolves)
        node_type = node.__class__.__name__
        if node_types_set and node_type.lower() not in node_types_set:
            if depth > 0:
                for child_index, child in enumerate(node.children):
                    visit(child, depth + 1, path_indices + (child_index,))
                return
            # depth == 0: fall through to index root for ROOT_NODE_ID_SENTINEL

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

        parent = parents.get(node)

        # Preserve node_id when rebuilding after modify: unchanged nodes keep id,
        # replaced node keeps id for the new content at same start position
        node_id: Optional[str] = None
        marker_path = build_marker_path(path_indices)
        exact_key = build_exact_node_key(
            start_line,
            start_col,
            end_line,
            end_col,
            node_type,
        )
        if persisted_node_ids and marker_path in persisted_node_ids:
            node_id = persisted_node_ids[marker_path]
        elif exact_key in exact_key_to_id:
            node_id = exact_key_to_id.pop(exact_key)
        elif replaced_map:
            start_key = (start_line, start_col, node_type)
            if start_key in replaced_map:
                node_id = replaced_map.pop(start_key)
        if node_id is None:
            node_id = str(uuid.uuid4())
        node_to_uuid[id(node)] = node_id

        tree.node_map[node_id] = node
        parent_id = node_to_uuid.get(id(parent)) if parent else None
        tree.parent_map[node_id] = parent_id

        name = get_node_name(node)
        qualname = get_node_qualname(node, class_stack, func_stack)
        kind = get_node_kind(node, class_stack)

        # Track class/function stacks before visiting children
        entered_class = False
        entered_func = False
        if isinstance(node, cst.ClassDef):
            class_stack.append(node.name.value)
            entered_class = True
        elif isinstance(node, cst.FunctionDef):
            func_stack.append(node.name.value)
            entered_func = True

        # Visit children first so they are registered in node_to_uuid
        for child_index, child in enumerate(node.children):
            visit(child, depth + 1, path_indices + (child_index,))

        # Build children_ids from registered children (only when include_children)
        children_ids = (
            [node_to_uuid[id(c)] for c in node.children if id(c) in node_to_uuid]
            if include_children
            else []
        )

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
            children_ids=children_ids,
            parent_id=parent_id,
        )
        tree.metadata_map[node_id] = metadata
        if depth == 0:
            tree.root_node_id = node_id

        if entered_func:
            func_stack.pop()
        if entered_class:
            class_stack.pop()

    visit(tree.module, 0, (0,))


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
    logical_source, persisted_node_ids = strip_persisted_node_ids(source)
    module = cst.parse_module(logical_source)
    previous_metadata_map = dict(tree.metadata_map)

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
        previous_metadata_map=previous_metadata_map,
        persisted_node_ids=persisted_node_ids,
    )

    return tree


def rollback_tree_to_code(
    tree_id: str,
    code: str,
    node_types: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_children: bool = True,
) -> bool:
    """
    Restore in-memory tree to the given source code (rollback after failed save).

    Replaces tree.module with parsed code and rebuilds index. Use when save
    fails after modify so the tree is reverted to pre-modify state.

    Args:
        tree_id: Tree ID to roll back
        code: Full module source code to restore
        node_types: Optional filter for index (same as load)
        max_depth: Optional max depth for index
        include_children: Whether to index children

    Returns:
        True if tree was found and rolled back, False if tree not found
    """
    tree = get_tree(tree_id)
    if not tree:
        return False
    logical_source, persisted_node_ids = strip_persisted_node_ids(code)
    previous_metadata_map = dict(tree.metadata_map)
    tree.module = cst.parse_module(logical_source)
    tree.node_map.clear()
    tree.metadata_map.clear()
    tree.parent_map.clear()
    _build_tree_index(
        tree,
        node_types=node_types,
        max_depth=max_depth,
        include_children=include_children,
        previous_metadata_map=previous_metadata_map,
        persisted_node_ids=persisted_node_ids,
    )
    return True
