"""
Module extractor.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Any, Dict, Optional


def _find_method_in_class(
    self, class_node: ast.ClassDef, method_name: str
) -> Optional[Any]:
    """Find a method node in a class (supports both sync and async)."""
    for item in class_node.body:
        if (
            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == method_name
        ):
            return item
    return None


def validate_completeness(
    self,
    src_class_name: str,
    config: Dict[str, Any],
    original_props: set,
    original_methods: set,
) -> tuple[bool, Optional[str]]:
    """
    Validate that all original properties and methods are present.

    Uses pre-collected original_props and original_methods for strict
    validation against the refactored code.
    """
    try:
        # Reload file to get new AST
        with open(self.file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(self.file_path))

        # Find source class in new tree
        new_src_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == src_class_name:
                new_src_class = node
                break

        if not new_src_class:
            return False, f"Source class '{src_class_name}' not found after split"

        # Find all destination classes
        dst_classes = {}
        for dst_class_name in config.get("dst_classes", {}).keys():
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                    dst_classes[dst_class_name] = node
                    break

        # Collect properties and methods from new classes
        new_props = set()
        new_methods = set()

        # From source class (remaining + property references)
        new_src_props = set(self.extract_init_properties(new_src_class))
        new_props.update(new_src_props)

        # Check for property references (dst_class_name.lower() attributes)
        for item in new_src_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    # This is a property reference
                                    new_props.add(target.attr)

        # From destination classes
        for dst_class_name, dst_class_node in dst_classes.items():
            dst_props = set(self.extract_init_properties(dst_class_node))
            new_props.update(dst_props)

            for item in dst_class_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    new_methods.add(item.name)

        # From source class methods (wrappers + remaining)
        for item in new_src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_methods.add(item.name)

        # Validate properties - strict check
        missing_props = original_props - new_props
        if missing_props:
            return (
                False,
                f"Missing properties after split: {missing_props}. "
                f"Original: {len(original_props)}, Found: {len(new_props)}",
            )

        # Validate methods (excluding special methods) - strict check
        special_methods = {"__init__", "__new__", "__del__"}
        regular_original = original_methods - special_methods
        regular_new = new_methods - special_methods
        missing_methods = regular_original - regular_new
        if missing_methods:
            return (
                False,
                f"Missing methods after split: {missing_methods}. "
                f"Original: {len(regular_original)}, Found: {len(regular_new)}",
            )

        return True, None

    except Exception as e:
        return False, f"Error during completeness validation: {str(e)}"


def validate_docstrings(
    self,
    src_class: ast.ClassDef,
    config: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """
    Validate that all docstrings are preserved in destination classes.

    Args:
        src_class: Original source class AST node
        config: Split configuration

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Reload file to get new AST
        with open(self.file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(self.file_path))

        # Get source class docstring
        src_class_docstring = ast.get_docstring(src_class)

        # Get all method docstrings from source class
        src_method_docstrings = {}
        for item in src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_docstring = ast.get_docstring(item)
                if method_docstring:
                    src_method_docstrings[item.name] = method_docstring

        # Find all destination classes
        dst_classes = {}
        dst_classes_config = config.get("dst_classes", {})
        for dst_class_name in dst_classes_config.keys():
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                    dst_classes[dst_class_name] = node
                    break

        # Check class docstring in destination classes
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
                return False, (
                    f"Class docstring not found in destination classes. "
                    f"Expected: {src_class_docstring[:50]}..."
                )

        # Check method docstrings in destination classes
        method_mapping: Dict[str, str] = {}  # method_name -> dst_class_name
        for dst_class_name, dst_config in dst_classes_config.items():
            for method in dst_config.get("methods", []):
                method_mapping[method] = dst_class_name

        for method_name, method_docstring in src_method_docstrings.items():
            if method_name in method_mapping:
                dst_class_name = method_mapping[method_name]
                dst_class_node = dst_classes.get(dst_class_name)

                if not dst_class_node:
                    return False, (
                        f"Destination class '{dst_class_name}' not found "
                        f"for method '{method_name}'"
                    )

                # Find method in destination class
                method_found = False
                for item in dst_class_node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        dst_method_docstring = ast.get_docstring(item)
                        if not dst_method_docstring:
                            return False, (
                                f"Method '{method_name}' docstring missing "
                                f"in destination class '{dst_class_name}'. "
                                f"Expected: {method_docstring[:50]}..."
                            )
                        if dst_method_docstring.strip() != method_docstring.strip():
                            return False, (
                                f"Method '{method_name}' docstring mismatch "
                                f"in destination class '{dst_class_name}'. "
                                f"Expected: {method_docstring[:50]}..., "
                                f"Got: {dst_method_docstring[:50]}..."
                            )
                        method_found = True
                        break

                if not method_found:
                    return False, (
                        f"Method '{method_name}' not found "
                        f"in destination class '{dst_class_name}'"
                    )

        return True, None

    except Exception as e:
        return False, f"Error during docstring validation: {str(e)}"
