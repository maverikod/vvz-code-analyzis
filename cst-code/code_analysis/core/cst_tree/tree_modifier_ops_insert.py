"""
Insert nodes into CST module (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import logging

from typing import Optional, cast

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider


from .models import CSTTree

from .tree_modifier_ops_find import find_parent_in_module_by_position

from .tree_modifier_ops_parse import parse_code_snippet_or_comment


logger = logging.getLogger(__name__)


def insert_node_at_position(
    module: cst.Module,
    tree: CSTTree,
    parent_node_id: str,
    new_code: str,
    position: str = "last",
    position_after_index: Optional[int] = None,
) -> cst.Module:
    """
    Insert one or more nodes at a precise index in parent's body.

    position: "first" (index 0), "last" (append), or "after" (after sibling at position_after_index).
    If position is "after" and position_after_index is out of range, treat as last.
    Resolves parent from current module by position when possible (batch insert).
    Supports: Module, IndentedBlock, or any compound statement whose body is IndentedBlock
    (FunctionDef, ClassDef, If, For, While, With, Try, ExceptHandler, Else, Finally, MatchCase).
    Does NOT support: SimpleStatementSuite (one-liners), Match (use MatchCase instead).
    """
    parent_node: Optional[cst.CSTNode] = None
    meta = tree.metadata_map.get(parent_node_id)
    if meta and hasattr(meta, "start_line") and hasattr(meta, "start_col"):
        parent_node = find_parent_in_module_by_position(
            module, meta.start_line, meta.start_col
        )
    if parent_node is None:
        parent_node = tree.node_map.get(parent_node_id)
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    # node_map may hold a distinct Module instance than the ``module`` being
    # transformed; PositionInserter matches by object identity in leave_*.
    if isinstance(parent_node, cst.Module):
        parent_node = module

    new_statements = parse_code_snippet_or_comment(code=new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    if isinstance(parent_node, cst.Module):
        body = list(parent_node.body)
    elif isinstance(parent_node, cst.IndentedBlock):
        body = list(parent_node.body)  # type: ignore[arg-type]
    elif isinstance(parent_node, cst.SimpleStatementSuite):
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            f"is a one-liner block (SimpleStatementSuite). "
            f"Expand the block to IndentedBlock first, then insert."
        )
    elif isinstance(parent_node, cst.Match):
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            f"is a Match statement. Use MatchCase node as parent_node_id instead."
        )
    elif hasattr(parent_node, "body") and isinstance(
        getattr(parent_node, "body", None), cst.IndentedBlock
    ):
        body = list(parent_node.body.body)  # type: ignore[arg-type]
    else:
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            f"has no insertable statement body. "
            f"Supported: Module, IndentedBlock, or any node whose body is IndentedBlock."
        )

    pos = position.strip().lower()
    if pos == "first":
        insert_index = 0
    elif pos == "after" and position_after_index is not None:
        insert_index = min(position_after_index + 1, len(body))
    else:
        insert_index = len(body)

    new_body = body[:insert_index] + list(new_statements) + body[insert_index:]

    class PositionInserter(cst.CSTTransformer):
        def __init__(
            self,
            target_parent: cst.CSTNode,
            replacement_body: list[cst.BaseStatement],
        ):
            self.target_parent = target_parent
            self.replacement_body = replacement_body
            self.done = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

        def leave_FunctionDef(
            self,
            original_node: cst.FunctionDef,
            updated_node: cst.FunctionDef,
        ) -> cst.FunctionDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.ClassDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            updated_node = super().on_leave(original_node, updated_node)
            if original_node is self.target_parent and not self.done:
                body_attr = getattr(updated_node, "body", None)
                if isinstance(body_attr, cst.IndentedBlock):
                    self.done = True
                    return updated_node.with_changes(
                        body=body_attr.with_changes(body=self.replacement_body)
                    )
            return updated_node

    inserter = PositionInserter(parent_node, cast(list, new_body))
    result = module.visit(inserter)
    if not inserter.done:
        raise ValueError(f"Nodes were not inserted into parent {parent_node_id}")
    return result


def insert_node(
    module: cst.Module, tree: CSTTree, parent_node_id: str, new_code: str, position: str
) -> cst.Module:
    """Insert one or more nodes into module (used when target_node_id is set)."""
    parent_node = tree.node_map.get(parent_node_id)
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    # Parse new code (supports multi-line); allow comment-only (EmptyLine with Comment)
    new_statements = parse_code_snippet_or_comment(code=new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    # Use LibCST transformer to insert the nodes
    class NodeInserter(cst.CSTTransformer):
        def __init__(
            self,
            target_parent: cst.CSTNode,
            new_statements: list[cst.BaseStatement],
            position: str,
        ):
            self.target_parent = target_parent
            self.new_statements = new_statements
            self.position = position
            self.inserted = False

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            if original_node is self.target_parent:
                # Insert nodes into parent's body
                if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
                    if isinstance(updated_node.body, cst.IndentedBlock):
                        body_list: list[cst.BaseStatement] = list(
                            updated_node.body.body
                        )
                        if self.position == "before":
                            body_list = list(self.new_statements) + body_list
                        else:  # after
                            body_list = body_list + list(self.new_statements)
                        self.inserted = True
                        return updated_node.with_changes(
                            body=cst.IndentedBlock(body=body_list)
                        )
                elif isinstance(updated_node, cst.Module):
                    # Insert at module level
                    body_list = list(updated_node.body)
                    if self.position == "before":
                        body_list = list(self.new_statements) + body_list
                    else:  # after
                        body_list = body_list + list(self.new_statements)
                    self.inserted = True
                    return updated_node.with_changes(body=body_list)
            return updated_node

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level insertions
            if original_node is self.target_parent:
                body_list: list[cst.BaseStatement] = list(updated_node.body)
                if self.position == "before":
                    body_list = list(self.new_statements) + body_list
                else:  # after
                    body_list = body_list + list(self.new_statements)
                self.inserted = True
                return updated_node.with_changes(body=body_list)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level insertions
            # Check if this block's parent is the target parent
            # This handles cases where we insert into nested blocks
            # The actual insertion is handled in on_leave for FunctionDef/ClassDef
            # But we also need to handle direct IndentedBlock insertions
            return updated_node

    inserter = NodeInserter(parent_node, cast(list, new_statements), position)
    result = module.visit(inserter)
    if not inserter.inserted:
        raise ValueError(f"Nodes were not inserted into {parent_node_id}")
    return result


def insert_node_relative(
    module: cst.Module,
    tree: CSTTree,
    target_node_id: str,
    parent_node_id: str,
    new_code: str,
    position: str,
) -> cst.Module:
    """Insert nodes before/after a target node in its parent's body.

    The target_node_id is automatically normalized: if it points to a node
    that is not a direct child of the body (e.g. Import inside SimpleStatementLine,
    or Name inside FunctionDef), we walk up parent_id in metadata_map until we
    find an ancestor that IS a direct statement-level child of some body.
    This means callers never need to manually pick the 'right level' — any
    node_id from anywhere in the subtree works correctly.
    """
    # ── 1. Resolve stale UUIDs via aliases ──────────────────────────────────
    resolved_target = tree.node_id_aliases.get(target_node_id, target_node_id)
    target_metadata = tree.metadata_map.get(resolved_target) or tree.metadata_map.get(
        target_node_id
    )
    if target_metadata is None:
        raise ValueError(f"Target node not found: {target_node_id}")

    # ── 2. Build module positions once ──────────────────────────────────────
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)

    # ── 3. Helper: get body list from any container node ────────────────────
    def _get_body(node: cst.CSTNode) -> Optional[list]:
        if isinstance(node, cst.Module):
            return list(node.body)
        if isinstance(node, cst.IndentedBlock):
            return list(node.body)
        body_attr = getattr(node, "body", None)
        if isinstance(body_attr, cst.IndentedBlock):
            return list(body_attr.body)
        return None

    # ── 4. Resolve parent node ───────────────────────────────────────────────
    resolved_parent = tree.node_id_aliases.get(parent_node_id, parent_node_id)
    parent_metadata = tree.metadata_map.get(resolved_parent) or tree.metadata_map.get(
        parent_node_id
    )
    parent_node: Optional[cst.CSTNode] = None
    if parent_metadata and hasattr(parent_metadata, "start_line"):
        parent_node = find_parent_in_module_by_position(
            module, parent_metadata.start_line, parent_metadata.start_col
        )
    if parent_node is None:
        parent_node = tree.node_map.get(resolved_parent) or tree.node_map.get(
            parent_node_id
        )
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    body = _get_body(parent_node)
    if body is None:
        raise ValueError(
            f"Parent node {parent_node_id} ({type(parent_node).__name__}) "
            "has no insertable statement body."
        )

    # ── 5. Normalize target to statement level ───────────────────────────────
    # Walk up parent_id chain until we find a node whose (start_line, start_col)
    # matches a direct element of `body`. This handles cases like:
    #   Import inside SimpleStatementLine  → normalize to SimpleStatementLine
    #   Name inside FunctionDef            → normalize to FunctionDef
    #   Any deeply nested node             → normalize to its statement ancestor
    def _find_in_body(meta_start_line: int, meta_start_col: int) -> int:
        """Return index of body element whose position matches, or -1."""
        for i, stmt in enumerate(body):
            pos = positions.get(stmt)
            if pos is None:
                continue
            if pos.start.line == meta_start_line and pos.start.column == meta_start_col:
                return i
        return -1

    # Start from the given target and walk up until we hit the body level
    current_meta = target_metadata
    target_index = -1
    while current_meta is not None:
        target_index = _find_in_body(current_meta.start_line, current_meta.start_col)
        if target_index >= 0:
            break
        # Not found at this level — go one level up
        parent_id_up = current_meta.parent_id
        if parent_id_up is None:
            break
        current_meta = tree.metadata_map.get(parent_id_up)
        if current_meta is None:
            break
        # Stop if we've reached or passed the parent body container itself
        # (no point going above the body we're inserting into)
        if current_meta.node_id in (resolved_parent, parent_node_id):
            break

    if target_index < 0:
        parent_type = type(parent_node).__name__
        raise ValueError(
            f"Cannot find target node {target_node_id} (or any of its ancestors) "
            f"as a direct statement in parent {parent_node_id} ({parent_type}). "
            f"Target type: {target_metadata.type}, "
            f"target position: {target_metadata.start_line}:{target_metadata.start_col}."
        )

    # ── 6. Build new body and apply ─────────────────────────────────────────
    new_statements = parse_code_snippet_or_comment(code=new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    insert_at = target_index if position == "before" else target_index + 1
    new_body = body[:insert_at] + list(new_statements) + body[insert_at:]

    class PositionInserter(cst.CSTTransformer):
        def __init__(self, target_parent: cst.CSTNode, replacement_body: list) -> None:
            self.target_parent = target_parent
            self.replacement_body = replacement_body
            self.done = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.ClassDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.FunctionDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=updated_node.body.with_changes(body=self.replacement_body)
                )
            return updated_node

        def leave_IndentedBlock(
            self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock
        ) -> cst.IndentedBlock:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(body=self.replacement_body)
            return updated_node

    inserter = PositionInserter(parent_node, cast(list, new_body))
    result = module.visit(inserter)
    if not inserter.done:
        raise ValueError(f"Nodes were not inserted into parent {parent_node_id}")
    return result
