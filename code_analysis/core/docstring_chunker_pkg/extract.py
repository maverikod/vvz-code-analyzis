"""
Module extract.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Any, Dict, List, Optional, Tuple


def _find_node_context(
    self, node: ast.AST, tree: ast.Module
) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """
    Find context for AST node (class_id, function_id, method_id).

    Args:
        node: AST node
        tree: AST module

    Returns:
        Tuple of (class_id, function_id, method_id, line)
    """
    class_id = None
    function_id = None
    method_id = None
    line = getattr(node, "lineno", None)

    # Walk tree to find parent context
    for parent in ast.walk(tree):
        if isinstance(parent, ast.ClassDef):
            # Check if node is within this class
            if hasattr(node, "lineno") and hasattr(parent, "lineno"):
                if parent.lineno <= node.lineno:
                    # Check if node is in class body
                    if hasattr(parent, "end_lineno") and parent.end_lineno:
                        if node.lineno <= parent.end_lineno:
                            # Get class_id from database
                            # We'll need to pass this information differently
                            class_id = parent.name  # Store name, resolve ID later
                    else:
                        # Fallback: check if node is in class body by walking
                        for item in parent.body:
                            if item == node or (
                                hasattr(item, "lineno")
                                and hasattr(node, "lineno")
                                and item.lineno == node.lineno
                            ):
                                class_id = parent.name
                                # Check if it's a method
                                if isinstance(
                                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                                ):
                                    method_id = node.name
                                break

        elif isinstance(parent, ast.FunctionDef) and not class_id:
            # Top-level function
            if hasattr(node, "lineno") and hasattr(parent, "lineno"):
                if parent.lineno == node.lineno and parent == node:
                    function_id = parent.name

    return (class_id, function_id, method_id, line)


def extract_docstrings_and_comments(
    self, tree: ast.Module, file_content: str
) -> List[Dict[str, Any]]:
    """
    Extract all docstrings and comments from AST with context binding.

    Args:
        tree: AST module node
        file_content: Original file content

    Returns:
        List of extracted text items with metadata including AST node binding
    """
    items = []
    lines = file_content.split("\n")

    # Extract file-level docstring
    file_docstring = ast.get_docstring(tree)
    if file_docstring:
        items.append(
            {
                "type": "file_docstring",
                "text": file_docstring,
                "line": 1,
                "ast_node_type": "Module",
                "entity_type": "file",
                "entity_name": None,
                "class_name": None,
                "function_name": None,
                "method_name": None,
            }
        )

    # Extract docstrings and comments from all nodes with context
    # Use recursive visitor to maintain parent context
    def visit_node(
        node: ast.AST,
        parent_class: Optional[str] = None,
        parent_function: Optional[str] = None,
    ):
        """Recursively visit AST nodes with parent context."""
        node_type = type(node).__name__

        # Extract docstrings (only from nodes that can have docstrings)
        # ast.get_docstring() works only for Module, ClassDef, FunctionDef, AsyncFunctionDef
        # In Python 3.12+, it raises ValueError for nodes that can't have docstrings
        docstring = None
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            try:
                docstring = ast.get_docstring(node)
            except (ValueError, TypeError, AttributeError):
                # Some nodes can't have docstrings (e.g., Expr)
                # In Python 3.12+, ValueError is raised: "'Expr' can't have docstrings"
                # This is expected for nodes that don't support docstrings
                docstring = None

        if docstring:
            class_name = None
            function_name = None
            method_name = None
            entity_type = None
            entity_name = None

            if isinstance(node, ast.ClassDef):
                entity_type = "class"
                entity_name = node.name
                class_name = node.name
                # Recursively visit class body with class context
                for child in node.body:
                    visit_node(child, parent_class=node.name, parent_function=None)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entity_name = node.name
                if parent_class:
                    # It's a method
                    entity_type = "method"
                    method_name = node.name
                    class_name = parent_class
                else:
                    # It's a function
                    entity_type = "function"
                    function_name = node.name
                # Recursively visit function body
                for child in node.body:
                    visit_node(
                        child, parent_class=parent_class, parent_function=node.name
                    )
            else:
                # Module docstring (already handled above)
                return

            items.append(
                {
                    "type": "docstring",
                    "text": docstring,
                    "line": getattr(node, "lineno", None),
                    "ast_node_type": node_type,
                    "entity_type": entity_type,
                    "entity_name": entity_name,
                    "class_name": class_name,
                    "function_name": function_name,
                    "method_name": method_name,
                    "node": node,  # Keep reference for later ID resolution
                }
            )
        else:
            # Not a docstring node, but may have children
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    visit_node(child, parent_class=node.name, parent_function=None)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in node.body:
                    visit_node(
                        child, parent_class=parent_class, parent_function=node.name
                    )
            elif hasattr(node, "body") and isinstance(node.body, list):
                # Other nodes with body (e.g., If, For, While, etc.)
                for child in node.body:
                    visit_node(
                        child,
                        parent_class=parent_class,
                        parent_function=parent_function,
                    )

    # Start visiting from module body
    for node in tree.body:
        visit_node(node)

    # Extract comments with proper context binding
    def visit_node_for_comments(
        node: ast.AST,
        parent_class: Optional[str] = None,
        parent_function: Optional[str] = None,
    ):
        """Recursively visit AST nodes to extract comments with parent context."""
        if hasattr(node, "lineno"):
            node_line = node.lineno - 1
            if 0 <= node_line < len(lines):
                line = lines[node_line]
                # Check for inline comment
                if "#" in line:
                    comment_start = line.find("#")
                    comment_text = line[comment_start + 1 :].strip()
                    if comment_text:
                        # Use parent context from recursive traversal
                        class_name = parent_class
                        function_name = parent_function
                        method_name = None
                        entity_type = None

                        # Determine entity type based on context
                        if parent_class:
                            if isinstance(
                                node, (ast.FunctionDef, ast.AsyncFunctionDef)
                            ):
                                entity_type = "method_comment"
                                method_name = node.name
                            else:
                                entity_type = "class_comment"
                        elif parent_function:
                            entity_type = "function_comment"
                        else:
                            entity_type = "comment"

                        items.append(
                            {
                                "type": "comment",
                                "text": comment_text,
                                "line": node.lineno,
                                "ast_node_type": type(node).__name__,
                                "entity_type": entity_type,
                                "entity_name": None,
                                "class_name": class_name,
                                "function_name": function_name,
                                "method_name": method_name,
                                "node": node,
                            }
                        )

        # Recursively visit children with updated context
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                visit_node_for_comments(
                    child, parent_class=node.name, parent_function=None
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in node.body:
                visit_node_for_comments(
                    child, parent_class=parent_class, parent_function=node.name
                )
        elif hasattr(node, "body") and isinstance(node.body, list):
            for child in node.body:
                visit_node_for_comments(
                    child,
                    parent_class=parent_class,
                    parent_function=parent_function,
                )

    # Start visiting from module body for comments
    for node in tree.body:
        visit_node_for_comments(node)

    return items
