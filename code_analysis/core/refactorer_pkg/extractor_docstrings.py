"""
Validate docstrings preserved after superclass extraction.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple


def validate_docstrings_preserved(
    file_path: str,
    child_nodes: List[ast.ClassDef],
    config: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Validate that all docstrings are preserved in base and child classes.
    Returns (is_valid, error_message).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(file_path))
        base_class_name = config.get("base_class")
        extract_from = config.get("extract_from", {})
        base_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                base_class = node
                break
        if not base_class:
            return (
                False,
                f"Base class '{base_class_name}' not found after extraction",
            )
        for child_node in child_nodes:
            child_name = child_node.name
            child_config = extract_from.get(child_name, {})
            new_child_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == child_name:
                    new_child_class = node
                    break
            if not new_child_class:
                return (
                    False,
                    f"Child class '{child_name}' not found after extraction",
                )
            original_child_docstring = ast.get_docstring(child_node)
            if original_child_docstring:
                new_child_docstring = ast.get_docstring(new_child_class)
                if not new_child_docstring:
                    return (
                        False,
                        f"Child class '{child_name}' docstring missing. "
                        f"Expected: {original_child_docstring[:50]}...",
                    )
                if new_child_docstring.strip() != original_child_docstring.strip():
                    return (
                        False,
                        f"Child class '{child_name}' docstring mismatch. "
                        f"Expected: {original_child_docstring[:50]}..., "
                        f"Got: {new_child_docstring[:50]}...",
                    )
            extracted_methods = set(child_config.get("methods", []))
            all_extracted_methods = set()
            for cfg in extract_from.values():
                all_extracted_methods.update(cfg.get("methods", []))
            first_child = child_nodes[0] if child_nodes else None
            for method_name in extracted_methods:
                original_method = None
                for item in child_node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        original_method = item
                        break
                if original_method:
                    original_method_docstring = ast.get_docstring(original_method)
                    if original_method_docstring:
                        base_method = None
                        for item in base_class.body:
                            if (
                                isinstance(
                                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                                )
                                and item.name == method_name
                            ):
                                base_method = item
                                break
                        if not base_method:
                            return (
                                False,
                                f"Method '{method_name}' not found in base class "
                                f"'{base_class_name}' after extraction",
                            )
                        base_method_docstring = ast.get_docstring(base_method)
                        if not base_method_docstring:
                            return (
                                False,
                                f"Method '{method_name}' docstring missing in base class "
                                f"'{base_class_name}'. Expected: "
                                f"{original_method_docstring[:50]}...",
                            )
                        if (
                            method_name in all_extracted_methods
                            and first_child
                            and first_child is not child_node
                        ):
                            first_child_method = None
                            for item in first_child.body:
                                if (
                                    isinstance(
                                        item,
                                        (ast.FunctionDef, ast.AsyncFunctionDef),
                                    )
                                    and item.name == method_name
                                ):
                                    first_child_method = item
                                    break
                            if first_child_method:
                                first_child_docstring = ast.get_docstring(
                                    first_child_method
                                )
                                if first_child_docstring and (
                                    base_method_docstring.strip()
                                    != first_child_docstring.strip()
                                ):
                                    return (
                                        False,
                                        f"Method '{method_name}' docstring mismatch in base. "
                                        f"Expected (from first class '{first_child.name}'): "
                                        f"{first_child_docstring[:50]}..., "
                                        f"Got: {base_method_docstring[:50]}...",
                                    )
                        elif (
                            base_method_docstring.strip()
                            != original_method_docstring.strip()
                        ):
                            return (
                                False,
                                f"Method '{method_name}' docstring mismatch in base. "
                                f"Expected: {original_method_docstring[:50]}..., "
                                f"Got: {base_method_docstring[:50]}...",
                            )
        return (True, None)
    except Exception as e:
        return (False, f"Error during docstring validation: {str(e)}")
