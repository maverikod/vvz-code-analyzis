"""
CST tree modifier operations: replace, delete, insert helpers.

Extracted from tree_modifier for size limit. Used only by tree_modifier.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Union, cast

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from .models import CSTTree

logger = logging.getLogger(__name__)


def parse_code_snippet(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> list[cst.BaseStatement]:
    """
    Parse code snippet into list of statements.

    Supports both single statements and multi-line blocks.
    Handles indentation by normalizing it before parsing.

    Args:
        code: Code snippet to parse as single string (may have indentation).
        code_lines: Code snippet as list of lines (alternative to code).
                    Prevents JSON escaping issues with multi-line code.

    Returns:
        List of CST statements.

    Raises:
        ValueError: If code cannot be parsed or both code and code_lines are provided.

    Note:
        If code_lines is provided, it takes precedence over code.
        This allows passing multi-line code without JSON escaping issues.
    """
    # Prefer code_lines over code to avoid JSON escaping issues
    if code_lines is not None:
        if code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        code = "\n".join(code_lines)
    elif code is None:
        return []

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


def parse_code_snippet_or_comment(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> List[Union[cst.BaseStatement, cst.EmptyLine]]:
    """
    Parse code as statements, or as comment-only line(s) for insert.

    When the snippet is only comment(s) (e.g. "# mypy: ignore-errors"),
    parse_module returns empty body. This helper then builds EmptyLine+Comment
    node(s) so that insert can add comment lines to the module.

    Returns:
        List of statements or EmptyLine nodes (valid for Module.body).
    """
    statements = parse_code_snippet(code=code, code_lines=code_lines)
    if statements:
        return cast(List[Union[cst.BaseStatement, cst.EmptyLine]], statements)
    raw = ("\n".join(code_lines) if code_lines is not None else code) or ""
    stripped = raw.strip()
    if not stripped or not stripped.startswith("#"):
        return []
    # Comment-only: build EmptyLine(s) with Comment
    result: List[Union[cst.BaseStatement, cst.EmptyLine]] = []
    for line in stripped.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("#"):
            result.append(cst.EmptyLine(comment=cst.Comment(value=line_stripped)))
    return result


def delete_node(module: cst.Module, tree: CSTTree, node_id: str) -> cst.Module:
    """Delete a node from module."""
    metadata = tree.metadata_map.get(node_id)
    node = None
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

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel[cst.CSTNode]:
            if original_node is self.target_node:
                return cst.RemoveFromParent()
            return updated_node

    remover = NodeRemover(node)
    result = module.visit(remover)
    if not remover.removed:
        raise ValueError(f"Node {node_id} was not removed")
    return result


def find_node_in_module_by_position(
    module: cst.Module,
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
) -> Optional[cst.CSTNode]:
    """
    Find a node in the given module with exact position (for use after previous
    ops have updated the module so tree.node_map may point at stale nodes).
    Returns the statement-level node that appears in Module.body when the
    matched node is inside one (e.g. ImportFrom inside SimpleStatementLine),
    so that leave_Module finds it in original_node.body.
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]

    class Finder(cst.CSTVisitor):
        def visit(self, node: cst.CSTNode) -> bool:
            pos = positions.get(node)
            if pos is not None and hasattr(pos, "start") and hasattr(pos, "end"):
                if (
                    pos.start.line == start_line
                    and pos.start.column == start_col
                    and pos.end.line == end_line
                    and pos.end.column == end_col
                ):
                    # Prefer statement-level node so replace matches body items
                    if isinstance(node, cst.BaseStatement):
                        result[0] = node
                        return False
                    if result[0] is None:
                        result[0] = node
                    return True
            return True

    module.visit(Finder())
    found = result[0]
    # When no exact position match (e.g. after prior replace in batch), find by
    # start position so batch replace still resolves the correct statement.
    target_start = (start_line, start_col)
    if found is None:
        for stmt in module.body:
            pos = positions.get(stmt)
            if pos is None or not hasattr(pos, "start"):
                continue
            stmt_start = (pos.start.line, pos.start.column)
            if stmt_start == target_start:
                return stmt

        # Fallback: search whole tree for node with matching start (e.g. method
        # inside class body, after prior replace shifted end position).
        class FindByStart(cst.CSTVisitor):
            def visit(self, node: cst.CSTNode) -> bool:
                if isinstance(node, (cst.FunctionDef, cst.ClassDef)):
                    p = positions.get(node)
                    if (
                        p
                        and hasattr(p, "start")
                        and (
                            p.start.line,
                            p.start.column,
                        )
                        == target_start
                    ):
                        result[0] = node
                        return False
                return True

        result[0] = None
        module.visit(FindByStart())
        if result[0] is not None:
            return result[0]
        return None
    # When the matched node is inside a SimpleStatementLine (e.g. ImportFrom),
    # return the statement-level node so leave_Module finds it in module.body.
    if any(stmt is found for stmt in module.body):
        return found
    # Find the statement in module.body whose span contains this position.
    target_start = (start_line, start_col)
    target_end = (end_line, end_col)
    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None or not hasattr(pos, "start") or not hasattr(pos, "end"):
            continue
        stmt_start = (pos.start.line, pos.start.column)
        stmt_end = (pos.end.line, pos.end.column)
        if stmt_start <= target_start and target_end <= stmt_end:
            return stmt
    # Fallback: match by start position only (batch replace can leave end_col
    # differing between original metadata and current module).
    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None or not hasattr(pos, "start"):
            continue
        stmt_start = (pos.start.line, pos.start.column)
        if stmt_start == target_start:
            return stmt
    return found


def find_parent_in_module_by_position(
    module: cst.Module, start_line: int, start_col: int
) -> Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]]:
    """
    Find a container node (Module, FunctionDef, or ClassDef) in module
    with exact start position, or whose span contains the position (fallback
    after prior inserts may shift positions). Used for insert so we get the
    node from the current module after prior ops (node_map may be stale).
    """
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    result: List[Optional[cst.CSTNode]] = [None]
    # Fallback: candidates that contain (start_line, start_col), pick smallest
    candidates: List[Tuple[cst.CSTNode, int]] = []

    class ParentFinder(cst.CSTVisitor):
        def visit(self, node: cst.CSTNode) -> bool:
            if not isinstance(node, (cst.Module, cst.FunctionDef, cst.ClassDef)):
                return True
            pos = positions.get(node)
            if pos is None or not hasattr(pos, "start") or not hasattr(pos, "end"):
                return True
            sl, sc = pos.start.line, pos.start.column
            el, ec = pos.end.line, pos.end.column
            if sl == start_line and sc == start_col:
                result[0] = node
                return False
            # Span contains position (e.g. after prior insert line numbers shift)
            if (sl, sc) <= (start_line, start_col) <= (el, ec):
                span_size = (el - sl) * 10000 + (ec - sc)
                candidates.append((node, span_size))
            return True

    module.visit(ParentFinder())
    if result[0] is not None:
        return cast(
            Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]],
            result[0],
        )
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return cast(
            Optional[Union[cst.Module, cst.FunctionDef, cst.ClassDef]],
            candidates[0][0],
        )
    return None


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
        body = list(parent_node.body)  # type: ignore[arg-type,assignment]
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

    new_body = body[:insert_index] + list(new_statements) + body[insert_index:]  # type: ignore[arg-type]

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
                    body_list = list(updated_node.body)  # type: ignore[assignment,arg-type]
                    if self.position == "before":
                        body_list = list(self.new_statements) + body_list  # type: ignore[operator,arg-type]
                    else:  # after
                        body_list = body_list + list(self.new_statements)  # type: ignore[operator,arg-type]
                    self.inserted = True
                    return updated_node.with_changes(body=body_list)
            return updated_node

        def leave_Module(
            self, original_node: cst.Module, updated_node: cst.Module
        ) -> cst.Module:
            # Handle module-level insertions
            if original_node is self.target_parent:
                body_list: List[cst.BaseStatement] = list(updated_node.body)
                if self.position == "before":
                    body_list = list(self.new_statements) + body_list  # type: ignore[operator,arg-type]
                else:  # after
                    body_list = body_list + list(self.new_statements)  # type: ignore[operator,arg-type]
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
                    )  # type: ignore[operator]
                else:  # after
                    new_body = (
                        body[: target_index + 1]
                        + list(self.new_statements)
                        + body[target_index + 1 :]
                    )  # type: ignore[operator]
                self.inserted = True
                return updated_node.with_changes(body=new_body)
            return updated_node

        def on_leave(  # type: ignore[override]
            self, original_node: cst.CSTNode, updated_node: cst.CSTNode
        ) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel:
            if original_node is self.parent_node:
                if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
                    if isinstance(updated_node.body, cst.IndentedBlock):
                        body = list(updated_node.body.body)  # type: ignore[arg-type]
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
