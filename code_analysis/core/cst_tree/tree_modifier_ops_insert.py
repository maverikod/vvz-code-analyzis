"""
Insert nodes into CST module (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Optional, cast

import libcst as cst

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

    new_statements = parse_code_snippet_or_comment(code=new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    if isinstance(parent_node, cst.Module):
        body = list(parent_node.body)
    elif isinstance(parent_node, (cst.FunctionDef, cst.ClassDef)) and isinstance(
        parent_node.body, cst.IndentedBlock
    ):
        body = list(parent_node.body.body)  # type: ignore[arg-type]
    else:
        raise ValueError(
            f"Parent node {parent_node_id} has no insertable body (Module or IndentedBlock)"
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
                    body=cst.IndentedBlock(body=self.replacement_body)
                )
            return updated_node

        def leave_ClassDef(
            self, original_node: cst.ClassDef, updated_node: cst.ClassDef
        ) -> cst.ClassDef:
            if original_node is self.target_parent:
                self.done = True
                return updated_node.with_changes(
                    body=cst.IndentedBlock(body=self.replacement_body)
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
    """Insert nodes relative to a target node (before/after it in parent's body)."""
    target_node = tree.node_map.get(target_node_id)
    if not target_node:
        raise ValueError(f"Target node not found: {target_node_id}")

    # Get actual parent of target node (more reliable than using provided parent_node_id)
    target_metadata = tree.metadata_map.get(target_node_id)
    actual_parent_id = target_metadata.parent_id if target_metadata else None

    # Use provided parent_node_id if it matches actual parent, otherwise use actual parent
    if actual_parent_id and actual_parent_id != parent_node_id:
        # Log warning but use actual parent for insertion
        logger.warning(
            f"Parent mismatch: provided {parent_node_id}, actual {actual_parent_id}. "
            f"Using actual parent for insertion."
        )
        parent_node_id = actual_parent_id

    parent_node = tree.node_map.get(parent_node_id)
    if not parent_node:
        raise ValueError(
            f"Parent node not found: {parent_node_id}. "
            f"Target node's actual parent: {actual_parent_id}"
        )

    # Parse new code (supports multi-line); allow comment-only (EmptyLine with Comment)
    new_statements = parse_code_snippet_or_comment(code=new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    # Get target node metadata for position-based search
    target_metadata = tree.metadata_map.get(target_node_id)
    target_start_line = target_metadata.start_line if target_metadata else None
    target_name = None
    if isinstance(target_node, (cst.FunctionDef, cst.ClassDef)):
        target_name = (
            target_node.name.value if hasattr(target_node.name, "value") else None
        )

    # Find target node index in original module body for fallback search
    # This helps when identity check fails (LibCST creates new objects)
    target_index_in_original = -1
    if isinstance(parent_node, cst.Module):
        for i, stmt in enumerate(parent_node.body):
            # Check by identity first
            if stmt is target_node:
                target_index_in_original = i
                logger.debug(f"Found target node by identity at index {i}")
                break
            # Also check by name for FunctionDef/ClassDef
            if (
                target_name
                and isinstance(stmt, type(target_node))
                and hasattr(stmt, "name")
            ):
                try:
                    stmt_name = stmt.name.value if hasattr(stmt.name, "value") else None
                    if stmt_name == target_name:
                        target_index_in_original = i
                        logger.debug(f"Found target node by name at index {i}")
                        break
                except Exception:
                    pass

        logger.debug(
            f"Pre-computed target_index_in_original: {target_index_in_original} "
            f"(target_name: {target_name}, parent body length: {len(parent_node.body)})"
        )

    # Use LibCST transformer to insert relative to target node
    class RelativeNodeInserter(cst.CSTTransformer):
        def __init__(
            self,
            target_node: cst.CSTNode,
            parent_node: cst.CSTNode,
            new_statements: list[cst.BaseStatement],
            position: str,
            target_start_line: Optional[int] = None,
            target_name: Optional[str] = None,
            target_index_in_original: int = -1,
        ):
            self.target_node = target_node
            self.parent_node = parent_node
            self.new_statements = new_statements
            self.position = position
            self.target_start_line = target_start_line
            self.target_name = target_name
            self.target_index_in_original = target_index_in_original
            self.inserted = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level insertions relative to target node
            logger.debug(
                f"leave_Module called: target_name={self.target_name}, "
                f"target_index_in_original={self.target_index_in_original}, "
                f"body_length={len(original_node.body)}"
            )
            body = list(original_node.body)
            target_index = -1

            if (
                self.target_index_in_original >= 0
                and self.target_index_in_original < len(body)
            ):
                target_index = self.target_index_in_original
                logger.debug(
                    f"Using pre-computed index {target_index} for target node {self.target_name}"
                )

            if target_index < 0:
                for i, stmt in enumerate(body):
                    if stmt is self.target_node:
                        target_index = i
                        logger.debug(
                            f"Found target node by identity at index {i} in leave_Module"
                        )
                        break

            if target_index < 0:
                for i, stmt in enumerate(body):
                    if isinstance(stmt, type(self.target_node)):
                        if self.target_name and hasattr(stmt, "name"):
                            try:
                                if hasattr(stmt.name, "value"):
                                    stmt_name = stmt.name.value
                                elif isinstance(stmt.name, str):
                                    stmt_name = stmt.name
                                else:
                                    stmt_name = None

                                if stmt_name == self.target_name:
                                    target_index = i
                                    logger.debug(
                                        f"Found target node by name at index {i}"
                                    )
                                    break
                            except Exception:
                                pass

            if target_index >= 0:
                logger.debug(
                    f"Found target node at index {target_index} in module body (name: {self.target_name}, "
                    f"position: {self.position}, new_statements: {len(self.new_statements)})"
                )
                if self.position == "before":
                    new_body = cast(
                        list,
                        body[:target_index]
                        + list(self.new_statements)
                        + body[target_index:],
                    )
                else:  # after
                    new_body = cast(
                        list,
                        body[: target_index + 1]
                        + list(self.new_statements)
                        + body[target_index + 1 :],
                    )
                self.inserted = True
                logger.debug(
                    f"Inserted {len(self.new_statements)} statements, new body length: {len(new_body)}"
                )
                return updated_node.with_changes(body=new_body)
            else:
                logger.warning(
                    f"Target node not found in module body. "
                    f"Target name: {self.target_name}, "
                    f"Target type: {type(self.target_node).__name__}, "
                    f"Body length: {len(body)}, "
                    f"Pre-computed index: {self.target_index_in_original}"
                )
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            body = list(original_node.body)
            target_index = -1
            for i, stmt in enumerate(body):
                if stmt is self.target_node:
                    target_index = i
                    break

            if target_index >= 0:
                if self.position == "before":
                    new_body = (
                        body[:target_index]
                        + list(self.new_statements)
                        + body[target_index:]
                    )
                else:  # after
                    new_body = (
                        body[: target_index + 1]
                        + list(self.new_statements)
                        + body[target_index + 1 :]
                    )
                self.inserted = True
                return updated_node.with_changes(body=new_body)
            return updated_node

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel:
            if original_node is self.parent_node:
                if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
                    if isinstance(updated_node.body, cst.IndentedBlock):
                        body = list(updated_node.body.body)
                        target_index = -1
                        for i, stmt in enumerate(body):
                            if stmt is self.target_node:
                                target_index = i
                                break

                        if target_index >= 0:
                            if self.position == "before":
                                new_body = (
                                    body[:target_index]
                                    + list(self.new_statements)
                                    + body[target_index:]
                                )
                            else:  # after
                                new_body = (
                                    body[: target_index + 1]
                                    + list(self.new_statements)
                                    + body[target_index + 1 :]
                                )
                            self.inserted = True
                            return updated_node.with_changes(
                                body=cst.IndentedBlock(body=new_body)
                            )
            return updated_node

    # Get metadata for better error messages
    target_metadata = tree.metadata_map.get(target_node_id)
    parent_metadata = tree.metadata_map.get(parent_node_id)
    target_type = (
        target_metadata.type
        if target_metadata and hasattr(target_metadata, "type")
        else "unknown"
    )
    parent_type = (
        parent_metadata.type
        if parent_metadata and hasattr(parent_metadata, "type")
        else "unknown"
    )
    target_parent_id = target_metadata.parent_id if target_metadata else None

    # If we have a valid index and parent is Module, we can insert directly without transformer
    if isinstance(parent_node, cst.Module) and target_index_in_original >= 0:
        logger.debug(
            f"Using direct insertion for Module: index={target_index_in_original}, "
            f"position={position}, statements={len(new_statements)}"
        )
        body = list(parent_node.body)
        if target_index_in_original < len(body):
            if position == "before":
                new_body = cast(
                    list,
                    body[:target_index_in_original]
                    + list(new_statements)
                    + body[target_index_in_original:],
                )
            else:  # after
                new_body = cast(
                    list,
                    body[: target_index_in_original + 1]
                    + list(new_statements)
                    + body[target_index_in_original + 1 :],
                )
            return module.with_changes(body=new_body)
        else:
            logger.warning(
                f"target_index_in_original ({target_index_in_original}) >= body length ({len(body)})"
            )

    # Fallback: use transformer
    inserter = RelativeNodeInserter(
        target_node,
        parent_node,
        cast(list, new_statements),
        position,
        target_start_line=target_start_line,
        target_name=target_name,
        target_index_in_original=target_index_in_original,
    )
    result = module.visit(inserter)
    if not inserter.inserted:
        suggestion = ""
        if target_type == "SimpleStatementLine" and target_parent_id != parent_node_id:
            suggestion = (
                f" Hint: Target node's actual parent ({target_parent_id}) differs from "
                f"specified parent ({parent_node_id}). "
                f"Try using target_node_id without parent_node_id, or use the correct parent."
            )
        raise ValueError(
            f"Nodes were not inserted relative to target node {target_node_id} in parent {parent_node_id}. "
            f"Target node type: {target_type}, Parent node type: {parent_type}.{suggestion}"
        )
    return result
