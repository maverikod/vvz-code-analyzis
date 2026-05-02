"""Inline stable-id lifecycle: strip @node-id comments from CST module and restore before save.

Lifecycle:
  1. Load: parse file (comments present) -> _build_tree_index reads stable_id from leading_lines
             -> strip_inline_stable_ids(module) -> clean module in memory, stable_id in metadata_map
  2. Modify: model works with clean code, never sees @node-id comments
  3. Save: restore_inline_stable_ids(module, metadata_map) -> module with comments -> write to disk

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict

import libcst as cst

from .models import TreeNodeMetadata
from .node_stable_id import _STABLE_ID_RE, set_stable_id


class _StripInlineIds(cst.CSTTransformer):
    """Remove # @node-id: <uuid> from leading_lines of FunctionDef and ClassDef nodes."""

    def _strip_node(self, node: cst.CSTNode) -> cst.CSTNode:
        """Strip @node-id comment from leading_lines of the given node.

        Args:
            node: LibCST FunctionDef or ClassDef node

        Returns:
            Node with @node-id comment removed from leading_lines
        """
        filtered = [
            line for line in node.leading_lines
            if not (
                line.comment is not None
                and _STABLE_ID_RE.match(line.comment.value)
            )
        ]
        if len(filtered) == len(node.leading_lines):
            return node
        return node.with_changes(leading_lines=filtered)

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Remove @node-id comment from FunctionDef leading_lines.

        Args:
            original_node: Original FunctionDef node
            updated_node: Updated FunctionDef node

        Returns:
            FunctionDef with @node-id comment removed
        """
        return self._strip_node(updated_node)

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        """Remove @node-id comment from ClassDef leading_lines.

        Args:
            original_node: Original ClassDef node
            updated_node: Updated ClassDef node

        Returns:
            ClassDef with @node-id comment removed
        """
        return self._strip_node(updated_node)


def strip_inline_stable_ids(module: cst.Module) -> cst.Module:
    """Remove all # @node-id: comments from FunctionDef/ClassDef leading_lines.

    Called after _build_tree_index has already read stable_ids into metadata_map.
    Returns a clean module for in-memory use (model never sees @node-id comments).

    Args:
        module: LibCST module with @node-id comments

    Returns:
        Module with @node-id comments removed from all FunctionDef/ClassDef nodes
    """
    return module.visit(_StripInlineIds())


class _RestoreInlineIds(cst.CSTTransformer):
    """Insert # @node-id: <uuid> into leading_lines of FunctionDef and ClassDef nodes.

    Uses qualname as the lookup key into metadata_map.
    When the same qualname appears multiple times (e.g. overloaded names in different
    scopes), a counter ensures each occurrence gets its own stable_id.
    """

    def __init__(self, qualname_to_stable_id: Dict[str, list[str]]) -> None:
        """Initialize with qualname -> list of stable_ids mapping.

        Args:
            qualname_to_stable_id: Dict mapping qualname to ordered list of stable_ids
        """
        self._map = qualname_to_stable_id
        self._counters: Dict[str, int] = {}
        self._class_stack: list[str] = []
        self._func_stack: list[str] = []

    def _current_qualname(self, name: str, is_class: bool) -> str:
        """Build current qualname from context stacks.

        Args:
            name: Node name (function or class name)
            is_class: Whether node is a ClassDef

        Returns:
            Qualified name string
        """
        if self._class_stack:
            return ".".join(self._class_stack + [name])
        if not is_class and self._func_stack:
            parts = list(self._func_stack[:-1]) + [name]
            return ".".join(parts)
        return name

    def _restore_node(self, node: cst.CSTNode, qualname: str) -> cst.CSTNode:
        """Insert @node-id comment into node leading_lines if stable_id is available.

        Args:
            node: LibCST FunctionDef or ClassDef node
            qualname: Qualified name for lookup

        Returns:
            Node with @node-id comment inserted, or original node if not found
        """
        stable_ids = self._map.get(qualname)
        if not stable_ids:
            return node
        idx = self._counters.get(qualname, 0)
        if idx >= len(stable_ids):
            return node
        stable_id = stable_ids[idx]
        self._counters[qualname] = idx + 1
        return set_stable_id(node, stable_id)

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        """Push class name onto class stack before visiting children.

        Args:
            node: ClassDef node being visited

        Returns:
            True to continue traversal
        """
        self._class_stack.append(node.name.value)
        return True

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        """Pop class stack and restore @node-id comment.

        Args:
            original_node: Original ClassDef node
            updated_node: Updated ClassDef node

        Returns:
            ClassDef with @node-id comment restored
        """
        self._class_stack.pop()
        qualname = self._current_qualname(original_node.name.value, is_class=True)
        return self._restore_node(updated_node, qualname)

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        """Push function name onto func stack before visiting children.

        Args:
            node: FunctionDef node being visited

        Returns:
            True to continue traversal
        """
        self._func_stack.append(node.name.value)
        return True

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        """Pop func stack and restore @node-id comment.

        Args:
            original_node: Original FunctionDef node
            updated_node: Updated FunctionDef node

        Returns:
            FunctionDef with @node-id comment restored
        """
        self._func_stack.pop()
        qualname = self._current_qualname(original_node.name.value, is_class=False)
        return self._restore_node(updated_node, qualname)


def _build_qualname_to_stable_id(
    metadata_map: Dict[str, TreeNodeMetadata],
) -> Dict[str, list[str]]:
    """Build qualname -> ordered list of stable_ids from metadata_map.

    Only FunctionDef and ClassDef nodes carry stable_id comments.
    Multiple nodes with the same qualname are ordered by start_line.

    Args:
        metadata_map: Node metadata map from CSTTree

    Returns:
        Dict mapping qualname to list of stable_ids sorted by start_line
    """
    entries: list[tuple[str, int, str]] = []
    for meta in metadata_map.values():
        if meta.type not in ("FunctionDef", "ClassDef"):
            continue
        if meta.qualname is None:
            continue
        entries.append((meta.qualname, meta.start_line, meta.stable_id))
    entries.sort(key=lambda x: (x[0], x[1]))
    result: Dict[str, list[str]] = {}
    for qualname, _, stable_id in entries:
        result.setdefault(qualname, []).append(stable_id)
    return result


def restore_inline_stable_ids(
    module: cst.Module,
    metadata_map: Dict[str, TreeNodeMetadata],
) -> cst.Module:
    """Restore # @node-id: comments into FunctionDef/ClassDef leading_lines before save.

    Called in tree_saver just before serializing module to string.
    Does NOT mutate metadata_map or tree state.

    Args:
        module: Clean LibCST module (no @node-id comments)
        metadata_map: Node metadata map from CSTTree

    Returns:
        Module with @node-id comments restored in leading_lines
    """
    qualname_map = _build_qualname_to_stable_id(metadata_map)
    if not qualname_map:
        return module
    return module.visit(_RestoreInlineIds(qualname_map))
