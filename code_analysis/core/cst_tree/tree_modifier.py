"""
CST tree modifier - modify tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import List, Optional

import libcst as cst

from .models import CSTTree, TreeOperation, TreeOperationType
from .tree_builder import _build_tree_index, get_tree

logger = logging.getLogger(__name__)


def modify_tree(tree_id: str, operations: List[TreeOperation]) -> CSTTree:
    """
    Modify tree with atomic operations.

    All operations are validated before being applied.
    If any operation fails, all changes are rolled back.

    Args:
        tree_id: Tree ID
        operations: List of operations to apply

    Returns:
        Modified CSTTree

    Raises:
        ValueError: If any operation is invalid
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    # Validate all operations first
    for op in operations:
        _validate_operation(tree, op)

    # Create a copy of the module for modification
    # We'll apply all operations to this copy
    modified_module = tree.module

    try:
        # Apply all operations
        for op in operations:
            modified_module = _apply_operation(modified_module, tree, op)

        # Validate the modified module
        _validate_module(modified_module)

        # Update tree
        tree.module = modified_module

        # Rebuild index after modification
        # Clear old indices to avoid stale references
        tree.node_map.clear()
        tree.metadata_map.clear()
        tree.parent_map.clear()
        # Rebuild index with all nodes (no filters)
        _build_tree_index(tree, node_types=None, max_depth=None, include_children=True)

        return tree

    except Exception as e:
        logger.error(f"Error applying operations to tree {tree_id}: {e}")
        # Tree remains unchanged (we modified a copy)
        raise


def _parse_code_snippet(code: str) -> list[cst.BaseStatement]:
    """
    Parse code snippet into list of statements.

    Supports both single statements and multi-line blocks.
    Handles indentation by normalizing it before parsing.

    Args:
        code: Code snippet to parse (may have indentation).

    Returns:
        List of CST statements.

    Raises:
        ValueError: If code cannot be parsed.
    """
    if not code.strip():
        return []

    # Normalize indentation: find minimum common indentation and remove it
    lines = code.splitlines()
    if not lines:
        return []

    # Find minimum indentation (excluding empty lines)
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:  # Skip empty lines
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent

    # If all lines are empty or no indentation found, use original
    if min_indent is None or min_indent == 0:
        normalized = code
    else:
        # Remove minimum indentation from all lines
        normalized_lines = []
        for line in lines:
            if line.strip():  # Non-empty line
                if len(line) >= min_indent:
                    normalized_lines.append(line[min_indent:])
                else:
                    normalized_lines.append(line)
            else:  # Empty line
                normalized_lines.append("")
        normalized = "\n".join(normalized_lines)

    # Try parsing as module first
    try:
        mod = cst.parse_module(normalized)
        return list(mod.body)
    except cst.ParserSyntaxError:
        # If parsing as module fails, try wrapping in a function body
        # This handles cases where code is a statement sequence (not valid module-level)
        indented_lines = []
        for line in normalized.splitlines():
            if line.strip():
                indented_lines.append("    " + line)
            else:
                indented_lines.append("")
        func_body = "\n".join(indented_lines)
        func_wrapper = f"def _temp():\n{func_body}"

        try:
            mod = cst.parse_module(func_wrapper)
            if mod.body and isinstance(mod.body[0], cst.FunctionDef):
                func = mod.body[0]
                if isinstance(func.body, cst.IndentedBlock):
                    return list(func.body.body)
        except Exception:
            pass

        # Last resort: try as single statement
        try:
            stmt = cst.parse_statement(normalized)
            return [stmt]
        except Exception as e:
            raise ValueError(
                f"Failed to parse code snippet as statements: {e}. "
                "Code must be valid Python statements."
            ) from e


def _find_parent_for_node(tree: CSTTree, node_id: str) -> Optional[str]:
    """
    Find parent node_id for a given node_id.

    Args:
        tree: CSTTree
        node_id: Node ID to find parent for

    Returns:
        Parent node_id or None if not found
    """
    metadata = tree.metadata_map.get(node_id)
    if not metadata:
        return None
    return metadata.parent_id


def _validate_operation(tree: CSTTree, operation: TreeOperation) -> None:
    """Validate an operation before applying it."""
    if operation.action == TreeOperationType.DELETE:
        if operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for deletion: {operation.node_id}. "
                f"Available nodes (first 5): {available}"
            )
    elif operation.action == TreeOperationType.REPLACE:
        if operation.node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Node not found for replacement: {operation.node_id}. "
                f"Available nodes (first 5): {available}"
            )
        if not operation.code:
            raise ValueError("code required for replace operation")
        # Validate code syntax (supports multi-line)
        try:
            _parse_code_snippet(operation.code)
        except Exception as e:
            raise ValueError(f"Invalid code syntax for replace: {e}") from e
    elif operation.action == TreeOperationType.INSERT:
        if not operation.code:
            raise ValueError("code required for insert operation")
        # Either parent_node_id or target_node_id must be provided
        if not operation.parent_node_id and not operation.target_node_id:
            raise ValueError(
                "parent_node_id or target_node_id required for insert operation"
            )
        if operation.parent_node_id and operation.parent_node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Parent node not found: {operation.parent_node_id}. "
                f"Available nodes (first 5): {available}"
            )
        if operation.target_node_id and operation.target_node_id not in tree.node_map:
            available = list(tree.node_map.keys())[:5]
            raise ValueError(
                f"Target node not found: {operation.target_node_id}. "
                f"Available nodes (first 5): {available}"
            )
        if operation.position not in ("before", "after"):
            raise ValueError(
                "position must be 'before' or 'after' for insert operation"
            )
        # Validate code syntax (supports multi-line)
        try:
            _parse_code_snippet(operation.code)
        except Exception as e:
            raise ValueError(f"Invalid code syntax for insert: {e}") from e


def _apply_operation(
    module: cst.Module, tree: CSTTree, operation: TreeOperation
) -> cst.Module:
    """Apply a single operation to module."""
    if operation.action == TreeOperationType.DELETE:
        return _delete_node(module, tree, operation.node_id)
    elif operation.action == TreeOperationType.REPLACE:
        return _replace_node(module, tree, operation.node_id, operation.code)
    elif operation.action == TreeOperationType.INSERT:
        # If target_node_id is provided, find parent automatically and insert relative to target
        if operation.target_node_id:
            parent_id = _find_parent_for_node(tree, operation.target_node_id)
            if not parent_id:
                raise ValueError(
                    f"Cannot find parent for target node: {operation.target_node_id}"
                )
            return _insert_node_relative(
                module,
                tree,
                operation.target_node_id,
                parent_id,
                operation.code,
                operation.position,
            )
        else:
            # Use parent_node_id (existing logic)
            return _insert_node(
                module,
                tree,
                operation.parent_node_id,
                operation.code,
                operation.position,
            )
    else:
        raise ValueError(f"Unknown operation type: {operation.action}")


def _delete_node(module: cst.Module, tree: CSTTree, node_id: str) -> cst.Module:
    """Delete a node from module."""
    node = tree.node_map.get(node_id)
    if not node:
        raise ValueError(f"Node not found: {node_id}")

    # Use LibCST transformer to remove the node
    class NodeRemover(cst.CSTTransformer):
        def __init__(self, target_node: cst.CSTNode):
            self.target_node = target_node
            self.removed = False

        def on_visit(self, node: cst.CSTNode) -> bool:
            if node is self.target_node:
                self.removed = True
                return False
            return True

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            if original_node is self.target_node:
                return cst.RemoveFromParent()
            return updated_node

    remover = NodeRemover(node)
    result = module.visit(remover)
    if not remover.removed:
        raise ValueError(f"Node {node_id} was not removed")
    return result


def _replace_node(
    module: cst.Module, tree: CSTTree, node_id: str, new_code: str
) -> cst.Module:
    """Replace a node in module with one or more statements."""
    node = tree.node_map.get(node_id)
    if not node:
        raise ValueError(f"Node not found: {node_id}")

    # Parse new code (supports multi-line)
    new_statements = _parse_code_snippet(new_code)
    if not new_statements:
        # Empty code means delete
        return _delete_node(module, tree, node_id)

    # Use LibCST transformer to replace the node
    class NodeReplacer(cst.CSTTransformer):
        def __init__(
            self, target_node: cst.CSTNode, replacements: list[cst.BaseStatement]
        ):
            self.target_node = target_node
            self.replacements = replacements
            self.replaced = False

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
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
            if any(stmt is self.target_node for stmt in original_node.body):
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

        def leave_SimpleStatementLine(
            self,
            original_node: cst.SimpleStatementLine,
            updated_node: cst.SimpleStatementLine,
        ) -> cst.SimpleStatementLine:
            # If replacing SimpleStatementLine with multiple statements,
            # we need to replace it at the parent level (IndentedBlock/Module)
            # This is handled in leave_IndentedBlock/leave_Module
            return updated_node

    replacer = NodeReplacer(node, new_statements)
    result = module.visit(replacer)
    if not replacer.replaced:
        raise ValueError(f"Node {node_id} was not replaced")
    return result


def _insert_node(
    module: cst.Module, tree: CSTTree, parent_node_id: str, new_code: str, position: str
) -> cst.Module:
    """Insert one or more nodes into module."""
    parent_node = tree.node_map.get(parent_node_id)
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    # Parse new code (supports multi-line)
    new_statements = _parse_code_snippet(new_code)
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

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            if original_node is self.target_parent:
                # Insert nodes into parent's body
                if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
                    body = list(updated_node.body.body)
                    if self.position == "before":
                        body = list(self.new_statements) + body
                    else:  # after
                        body = body + list(self.new_statements)
                    self.inserted = True
                    return updated_node.with_changes(body=cst.IndentedBlock(body=body))
                elif isinstance(updated_node, cst.Module):
                    # Insert at module level
                    body = list(updated_node.body)
                    if self.position == "before":
                        body = list(self.new_statements) + body
                    else:  # after
                        body = body + list(self.new_statements)
                    self.inserted = True
                    return updated_node.with_changes(body=body)
            return updated_node

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level insertions
            if original_node is self.target_parent:
                body = list(updated_node.body)
                if self.position == "before":
                    body = list(self.new_statements) + body
                else:  # after
                    body = body + list(self.new_statements)
                self.inserted = True
                return updated_node.with_changes(body=body)
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

    inserter = NodeInserter(parent_node, new_statements, position)
    result = module.visit(inserter)
    if not inserter.inserted:
        raise ValueError(f"Nodes were not inserted into {parent_node_id}")
    return result


def _insert_node_relative(
    module: cst.Module,
    tree: CSTTree,
    target_node_id: str,
    parent_node_id: str,
    new_code: str,
    position: str,
) -> cst.Module:
    """Insert nodes relative to a target node (before/after it in parent's body)."""
    target_node = tree.node_map.get(target_node_id)
    parent_node = tree.node_map.get(parent_node_id)
    if not target_node:
        raise ValueError(f"Target node not found: {target_node_id}")
    if not parent_node:
        raise ValueError(f"Parent node not found: {parent_node_id}")

    # Parse new code (supports multi-line)
    new_statements = _parse_code_snippet(new_code)
    if not new_statements:
        raise ValueError("Cannot insert empty code")

    # Use LibCST transformer to insert relative to target node
    class RelativeNodeInserter(cst.CSTTransformer):
        def __init__(
            self,
            target_node: cst.CSTNode,
            parent_node: cst.CSTNode,
            new_statements: list[cst.BaseStatement],
            position: str,
        ):
            self.target_node = target_node
            self.parent_node = parent_node
            self.new_statements = new_statements
            self.position = position
            self.inserted = False

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level insertions relative to target node
            if original_node is self.parent_node:
                body = list(updated_node.body)
                # Find target node in body
                target_index = -1
                for i, stmt in enumerate(body):
                    if stmt is self.target_node:
                        target_index = i
                        break

                if target_index >= 0:
                    if self.position == "before":
                        body = (
                            body[:target_index]
                            + list(self.new_statements)
                            + body[target_index:]
                        )
                    else:  # after
                        body = (
                            body[: target_index + 1]
                            + list(self.new_statements)
                            + body[target_index + 1 :]
                        )
                    self.inserted = True
                    return updated_node.with_changes(body=body)
            return updated_node

        def leave_IndentedBlock(
            self,
            original_node: cst.IndentedBlock,
            updated_node: cst.IndentedBlock,
        ) -> cst.IndentedBlock:
            # Handle block-level insertions relative to target node
            # Check if this block belongs to the parent
            body = list(updated_node.body)
            # Find target node in body
            target_index = -1
            for i, stmt in enumerate(body):
                if stmt is self.target_node:
                    target_index = i
                    break

            if target_index >= 0:
                if self.position == "before":
                    body = (
                        body[:target_index]
                        + list(self.new_statements)
                        + body[target_index:]
                    )
                else:  # after
                    body = (
                        body[: target_index + 1]
                        + list(self.new_statements)
                        + body[target_index + 1 :]
                    )
                self.inserted = True
                return updated_node.with_changes(body=body)
            return updated_node

        def on_leave(
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode:
            # Handle insertions into FunctionDef/ClassDef bodies
            if original_node is self.parent_node:
                if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
                    body = list(updated_node.body.body)
                    # Find target node in body
                    target_index = -1
                    for i, stmt in enumerate(body):
                        if stmt is self.target_node:
                            target_index = i
                            break

                    if target_index >= 0:
                        if self.position == "before":
                            body = (
                                body[:target_index]
                                + list(self.new_statements)
                                + body[target_index:]
                            )
                        else:  # after
                            body = (
                                body[: target_index + 1]
                                + list(self.new_statements)
                                + body[target_index + 1 :]
                            )
                        self.inserted = True
                        return updated_node.with_changes(
                            body=cst.IndentedBlock(body=body)
                        )
            return updated_node

    inserter = RelativeNodeInserter(target_node, parent_node, new_statements, position)
    result = module.visit(inserter)
    if not inserter.inserted:
        raise ValueError(
            f"Nodes were not inserted relative to target node {target_node_id} in parent {parent_node_id}"
        )
    return result


def _validate_module(module: cst.Module) -> None:
    """Validate module by compiling it."""
    try:
        compile(module.code, "<string>", "exec")
    except SyntaxError as e:
        raise ValueError(f"Module validation failed: {e}") from e
