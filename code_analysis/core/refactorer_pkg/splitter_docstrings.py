"""
Docstring validation for class splitter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path
from typing import Any, Dict, Optional


def validate_docstrings_impl(
    file_path: Path,
    src_class: ast.ClassDef,
    config: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """
    Validate that all docstrings are preserved in destination classes.

    Args:
        file_path: Path to the refactored file.
        src_class: Original source class AST node.
        config: Split configuration.

    Returns:
        Tuple of (is_valid, error_message).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(file_path))
        src_class_docstring = ast.get_docstring(src_class)
        src_method_docstrings: Dict[str, str] = {}
        for item in src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_docstring = ast.get_docstring(item)
                if method_docstring:
                    src_method_docstrings[item.name] = method_docstring
        dst_classes: Dict[str, ast.ClassDef] = {}
        dst_classes_config = config.get("dst_classes", {})
        for dst_class_name in dst_classes_config.keys():
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                    dst_classes[dst_class_name] = node
                    break
        if src_class_docstring:
            found_in_dst = False
            for dst_class_name, dst_class_node in dst_classes.items():
                dst_docstring = ast.get_docstring(dst_class_node)
                if (
                    dst_docstring
                    and dst_docstring.strip() == src_class_docstring.strip()
                ):
                    found_in_dst = True
                    break
            if not found_in_dst:
                return (
                    False,
                    f"Class docstring not found in destination classes. "
                    f"Expected: {src_class_docstring[:50]}...",
                )
        method_mapping: Dict[str, str] = {}
        for dst_class_name, dst_config in dst_classes_config.items():
            for method in dst_config.get("methods", []):
                method_mapping[method] = dst_class_name
        for method_name, method_docstring in src_method_docstrings.items():
            if method_name in method_mapping:
                dst_class_name = method_mapping[method_name]
                dst_node = dst_classes.get(dst_class_name)
                if not dst_node:
                    return (
                        False,
                        f"Destination class '{dst_class_name}' not found "
                        f"for method '{method_name}'",
                    )
                method_found = False
                for item in dst_node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        dst_method_docstring = ast.get_docstring(item)
                        if not dst_method_docstring:
                            return (
                                False,
                                f"Method '{method_name}' docstring missing in "
                                f"destination class '{dst_class_name}'. "
                                f"Expected: {method_docstring[:50]}...",
                            )
                        if dst_method_docstring.strip() != method_docstring.strip():
                            return (
                                False,
                                f"Method '{method_name}' docstring mismatch in "
                                f"destination class '{dst_class_name}'.",
                            )
                        method_found = True
                        break
                if not method_found:
                    return (
                        False,
                        f"Method '{method_name}' not found in destination "
                        f"class '{dst_class_name}'",
                    )
        return (True, None)
    except Exception as e:
        return (False, f"Error during docstring validation: {str(e)}")
