"""
Replace nodes and ranges in CST module (for tree modifier operations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Optional

import libcst as cst

from .models import CSTTree
from .tree_modifier_ops_find import delete_node, find_node_in_module_by_position
from .tree_modifier_ops_parse import parse_code_snippet


def replace_node(
    module: cst.Module, tree: CSTTree, node_id: str, new_code: str
) -> cst.Module:
    """Replace a node in module with one or more statements."""
    metadata = tree.metadata_map.get(node_id)
    # Resolve target node: use node from current module by position when
    # available (after prior ops tree.node_map may point at stale module nodes).
    node: Optional[cst.CSTNode] = None
    if metadata and hasattr(metadata, "start_line"):
        node = find_node_in_module_by_position(
            module,
            metadata.start_line,
            metadata.start_col,
            metadata.end_line,
            metadata.end_col,
        )
    if node is None:
        node = tree.node_map.get(node_id)
    if not node:
        node_info = (
            f"Node type: {metadata.type if metadata else 'unknown'}, "
            if metadata
            else ""
        )
        available = list(tree.node_map.keys())[:5]
        raise ValueError(
            f"Node not found: {node_id}. {node_info}"
            f"Available nodes (first 5): {available}"
        )

    # Parse new code (supports multi-line)
    new_statements = parse_code_snippet(new_code)
    if not new_statements:
        # Empty code means delete
        return delete_node(module, tree, node_id)

    node_type = metadata.type if metadata else "unknown"
    parent_id = metadata.parent_id if metadata else None
    parent_metadata = tree.metadata_map.get(parent_id) if parent_id else None
    parent_type = parent_metadata.type if parent_metadata else "unknown"

    # Use LibCST transformer to replace the node
    class NodeReplacer(cst.CSTTransformer):
        def __init__(
            self, target_node: cst.CSTNode, replacements: list[cst.BaseStatement]
        ):
            self.target_node = target_node
            self.replacements = replacements
            self.replaced = False
            self.visited_blocks: list[tuple[str, cst.IndentedBlock]] = []

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel:
            # Single statement replacement handled here
            if original_node is self.target_node:
                if len(self.replacements) == 1:
                    self.replaced = True
                    return self.replacements[0]
                # Multiple statements handled in leave_Module/leave_IndentedBlock
            return updated_node

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level replacements
            if original_node is self.target_node or any(
                stmt is self.target_node for stmt in original_node.body
            ):
                new_body: list[cst.BaseStatement] = []
                for stmt in original_node.body:
                    if stmt is self.target_node:
                        new_body.extend(self.replacements)
                        self.replaced = True
                    else:
                        new_body.append(stmt)
                if self.replaced:
                    return updated_node.with_changes(body=new_body)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level replacements (including multiple statements)
            # Check both original and updated body to handle nested cases
            body_to_check = original_node.body
            if any(stmt is self.target_node for stmt in body_to_check):
                new_body: list[cst.BaseStatement] = []
                for stmt in body_to_check:
                    if stmt is self.target_node:
                        new_body.extend(self.replacements)
                        self.replaced = True
                    else:
                        new_body.append(stmt)
                if self.replaced:
                    return updated_node.with_changes(body=new_body)
            return updated_node

        def leave_SimpleStatementLine(
            self,
            original_node: cst.SimpleStatementLine,
            updated_node: cst.SimpleStatementLine,
        ) -> cst.SimpleStatementLine:
            # If replacing SimpleStatementLine with multiple statements,
            # we need to replace it at the parent level (IndentedBlock/Module)
            # This is handled in leave_IndentedBlock/leave_Module
            # Mark that we visited this node to help with debugging
            if original_node is self.target_node and len(self.replacements) > 1:
                # This will be handled by parent's leave_IndentedBlock/leave_Module
                return updated_node
            return updated_node

    replacer = NodeReplacer(node, new_statements)
    result = module.visit(replacer)
    if not replacer.replaced:
        # Provide detailed error message with context (node type, parent, line range, hint)
        start_line = getattr(metadata, "start_line", None)
        end_line = getattr(metadata, "end_line", None)
        line_range = (
            f"start_line={start_line}, end_line={end_line}"
            if start_line is not None and end_line is not None
            else "line range unknown"
        )
        suggestion = ""
        if node_type == "SimpleStatementLine" and len(new_statements) > 1:
            suggestion = (
                " Hint: Replacing SimpleStatementLine with multiple statements requires "
                "the node to be in a Module or IndentedBlock body. "
                "Try using replace_range operation or replace the parent block instead."
            )
        elif node_type in ("Import", "ImportFrom"):
            suggestion = (
                " Hint: Try query_cst with replace_with for import statements, "
                "or replace the containing SimpleStatementLine."
            )
        else:
            suggestion = (
                " Hint: Replace only works for direct body statements (e.g. in Module or "
                "IndentedBlock). For inner nodes use replace_range or replace the parent."
            )
        raise ValueError(
            f"Node {node_id} was not replaced. "
            f"Node type: {node_type}, Parent type: {parent_type}, {line_range}.{suggestion}"
        )
    return result


def replace_range(
    module: cst.Module,
    tree: CSTTree,
    start_node_id: str,
    end_node_id: str,
    new_code: str,
) -> cst.Module:
    """Replace a range of consecutive nodes with new code."""
    start_node = tree.node_map.get(start_node_id)
    end_node = tree.node_map.get(end_node_id)
    if not start_node:
        raise ValueError(f"Start node not found: {start_node_id}")
    if not end_node:
        raise ValueError(f"End node not found: {end_node_id}")

    # Get metadata for better error messages
    start_metadata = tree.metadata_map.get(start_node_id)
    end_metadata = tree.metadata_map.get(end_node_id)
    start_parent_id = start_metadata.parent_id if start_metadata else None
    end_parent_id = end_metadata.parent_id if end_metadata else None

    # Verify both nodes have the same parent
    if start_parent_id != end_parent_id:
        raise ValueError(
            f"Start and end nodes must have the same parent. "
            f"Start parent: {start_parent_id}, End parent: {end_parent_id}"
        )

    # Parse new code (supports multi-line)
    new_statements = parse_code_snippet(new_code)
    if not new_statements:
        # Empty code means delete the range
        # This would require deleting all nodes in range, which is complex
        # For now, raise an error
        raise ValueError(
            "Cannot replace range with empty code. Use delete operations instead."
        )

    # Use LibCST transformer to replace the range
    class RangeReplacer(cst.CSTTransformer):
        def __init__(
            self,
            start_node: cst.CSTNode,
            end_node: cst.CSTNode,
            replacements: list[cst.BaseStatement],
        ):
            self.start_node = start_node
            self.end_node = end_node
            self.replacements = replacements
            self.replaced = False
            self.in_range = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level range replacements
            body = list(original_node.body)
            start_idx = -1
            end_idx = -1

            # Find start and end indices
            for i, stmt in enumerate(body):
                if stmt is self.start_node:
                    start_idx = i
                if stmt is self.end_node:
                    end_idx = i
                    break  # End node found, stop searching

            if start_idx >= 0 and end_idx >= 0 and start_idx <= end_idx:
                # Replace range
                new_body = (
                    body[:start_idx] + list(self.replacements) + body[end_idx + 1 :]
                )
                self.replaced = True
                return updated_node.with_changes(body=new_body)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level range replacements
            body = list(original_node.body)
            start_idx = -1
            end_idx = -1

            # Find start and end indices
            for i, stmt in enumerate(body):
                if stmt is self.start_node:
                    start_idx = i
                if stmt is self.end_node:
                    end_idx = i
                    break  # End node found, stop searching

            if start_idx >= 0 and end_idx >= 0 and start_idx <= end_idx:
                # Replace range
                new_body = (
                    body[:start_idx] + list(self.replacements) + body[end_idx + 1 :]
                )
                self.replaced = True
                return updated_node.with_changes(body=new_body)
            return updated_node

    replacer = RangeReplacer(start_node, end_node, new_statements)
    result = module.visit(replacer)
    if not replacer.replaced:
        # Provide detailed error message (types, line range, hint)
        start_type = start_metadata.type if start_metadata else "unknown"
        end_type = end_metadata.type if end_metadata else "unknown"
        parent_meta = (
            tree.metadata_map.get(start_parent_id) if start_parent_id else None
        )
        parent_type = (
            parent_meta.type
            if parent_meta and hasattr(parent_meta, "type")
            else "unknown"
        )
        start_line = getattr(start_metadata, "start_line", None)
        start_end = getattr(start_metadata, "end_line", None)
        end_start = getattr(end_metadata, "start_line", None)
        end_line = getattr(end_metadata, "end_line", None)
        line_range = "line range unknown"
        if all(x is not None for x in (start_line, start_end, end_start, end_line)):
            line_range = (
                f"start node lines {start_line}-{start_end}, "
                f"end node lines {end_start}-{end_line}"
            )
        hint = (
            " Hint: Both nodes must be consecutive statements in the same parent "
            "block (Module or IndentedBlock body). Use replace for single nodes."
        )
        raise ValueError(
            f"Range from {start_node_id} to {end_node_id} was not replaced. "
            f"Start node type: {start_type}, End node type: {end_type}, "
            f"Parent type: {parent_type}, {line_range}.{hint}"
        )
    return result
