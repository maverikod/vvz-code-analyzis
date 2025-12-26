"""
Validation utilities for refactoring operations.

This module contains validation functions that can be used by different
refactoring tools (splitter, extractor, merger).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


def validate_python_syntax(file_path: Path) -> tuple[bool, Optional[str]]:
    """
    Validate Python syntax of a file.

    Args:
        file_path: Path to Python file to validate

    Returns:
        Tuple of (success, error_message)
    """
    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, result.stderr)
        return (True, None)
    except subprocess.TimeoutExpired:
        return (False, "Syntax validation timeout")
    except Exception as e:
        return (False, str(e))


def validate_imports(file_path: Path) -> tuple[bool, Optional[str]]:
    """
    Try to import the modified module.

    Args:
        file_path: Path to Python file to validate

    Returns:
        Tuple of (success, error_message)
    """
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as temp_file:
            shutil.copy2(file_path, temp_file.name)
            import sys

            sys.path.insert(0, str(file_path.parent))
            module_name = file_path.stem
            try:
                if module_name in sys.modules:
                    del sys.modules[module_name]
                __import__(module_name)
                return (True, None)
            except ImportError as e:
                return (False, str(e))
            finally:
                sys.path.remove(str(file_path.parent))
                if module_name in sys.modules:
                    del sys.modules[module_name]
    except Exception as e:
        return (False, str(e))


def extract_init_properties(class_node: ast.ClassDef) -> List[str]:
    """
    Extract properties initialized in __init__.

    Args:
        class_node: AST class node

    Returns:
        List of property names
    """
    properties = []
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            for stmt in item.body:
                # Handle regular assignments: self.attr = value
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Attribute):
                            if (
                                isinstance(target.value, ast.Name)
                                and target.value.id == "self"
                            ):
                                properties.append(target.attr)
                # Handle annotated assignments: self.attr: Type = value
                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Attribute):
                        if (
                            isinstance(stmt.target.value, ast.Name)
                            and stmt.target.value.id == "self"
                        ):
                            properties.append(stmt.target.attr)
    return properties


def validate_split_config(
    src_class: ast.ClassDef,
    config: Dict[str, Any],
    extract_init_properties_func,
) -> tuple[bool, List[str]]:
    """
    Validate split configuration.

    Args:
        src_class: Source class AST node
        config: Split configuration
        extract_init_properties_func: Function to extract init properties

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    if not config.get("src_class"):
        errors.append("src_class not specified")

    all_properties = set(extract_init_properties_func(src_class))
    all_methods = set()
    for item in src_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_methods.add(item.name)

    dst_properties = set()
    dst_methods = set()
    dst_classes = config.get("dst_classes", {})

    for dst_class_name, dst_config in dst_classes.items():
        dst_properties.update(dst_config.get("props", []))
        dst_methods.update(dst_config.get("methods", []))

    missing_props = all_properties - dst_properties
    if missing_props:
        errors.append(f"Missing properties in split config: {missing_props}")

    special_methods = {"__init__", "__new__", "__del__"}
    regular_methods = all_methods - special_methods
    missing_methods = regular_methods - dst_methods
    if missing_methods:
        errors.append(f"Missing methods in split config: {missing_methods}")

    extra_props = dst_properties - all_properties
    if extra_props:
        errors.append(f"Extra properties in config (not in class): {extra_props}")

    extra_methods = dst_methods - all_methods
    if extra_methods:
        errors.append(f"Extra methods in config (not in class): {extra_methods}")

    return (len(errors) == 0, errors)


def validate_extraction_config(
    config: Dict[str, Any], find_class_func
) -> tuple[bool, List[str]]:
    """
    Validate extraction configuration.

    Args:
        config: Extraction configuration
        find_class_func: Function to find class by name

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    base_class = config.get("base_class")
    if not base_class:
        errors.append("base_class not specified")

    child_classes = config.get("child_classes", [])
    if not child_classes:
        errors.append("child_classes list is empty")

    extract_from = config.get("extract_from", {})
    if not extract_from:
        errors.append("extract_from configuration is empty")

    for child in child_classes:
        if child not in extract_from:
            errors.append(f"Child class '{child}' not in extract_from")

    if find_class_func(base_class):
        errors.append(f"Base class '{base_class}' already exists")

    return (len(errors) == 0, errors)


def validate_merge_config(
    config: Dict[str, Any], find_class_func
) -> tuple[bool, List[str]]:
    """
    Validate merge configuration.

    Args:
        config: Merge configuration
        find_class_func: Function to find class by name

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    base_class = config.get("base_class")
    if not base_class:
        errors.append("base_class not specified")

    source_classes = config.get("source_classes", [])
    if not source_classes:
        errors.append("source_classes list is empty")

    if find_class_func(base_class):
        errors.append(f"Base class '{base_class}' already exists")

    for src_class in source_classes:
        if not find_class_func(src_class):
            errors.append(f"Source class '{src_class}' not found")

    return (len(errors) == 0, errors)


def validate_completeness_split(
    file_path: Path,
    src_class_name: str,
    config: Dict[str, Any],
    original_props: Set[str],
    original_methods: Set[str],
    extract_init_properties_func,
) -> tuple[bool, Optional[str]]:
    """
    Validate that all original properties and methods are present after split.

    Args:
        file_path: Path to modified file
        src_class_name: Name of source class
        config: Split configuration
        original_props: Set of original property names
        original_methods: Set of original method names
        extract_init_properties_func: Function to extract init properties

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(file_path))
        new_src_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == src_class_name:
                new_src_class = node
                break
        if not new_src_class:
            return (False, f"Source class '{src_class_name}' not found after split")

        dst_classes = {}
        for dst_class_name in config.get("dst_classes", {}).keys():
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                    dst_classes[dst_class_name] = node
                    break

        new_props = set()
        new_methods = set()
        new_src_props = set(extract_init_properties_func(new_src_class))
        new_props.update(new_src_props)

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
                                    new_props.add(target.attr)

        for dst_class_name, dst_class_node in dst_classes.items():
            dst_props = set(extract_init_properties_func(dst_class_node))
            new_props.update(dst_props)
            for item in dst_class_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    new_methods.add(item.name)

        for item in new_src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_methods.add(item.name)

        missing_props = original_props - new_props
        if missing_props:
            return (
                False,
                f"Missing properties after split: {missing_props}. Original: {len(original_props)}, Found: {len(new_props)}",
            )

        special_methods = {"__init__", "__new__", "__del__"}
        regular_original = original_methods - special_methods
        regular_new = new_methods - special_methods
        missing_methods = regular_original - regular_new
        if missing_methods:
            return (
                False,
                f"Missing methods after split: {missing_methods}. Original: {len(regular_original)}, Found: {len(regular_new)}",
            )

        return (True, None)
    except Exception as e:
        return (False, f"Error during completeness validation: {str(e)}")


def validate_completeness_extraction(
    file_path: Path,
    base_class_name: str,
    child_classes: List[str],
    config: Dict[str, Any],
    extract_init_properties_func,
) -> tuple[bool, Optional[str]]:
    """
    Validate that all members are present after extraction.

    Args:
        file_path: Path to modified file
        base_class_name: Name of base class
        child_classes: List of child class names
        config: Extraction configuration
        extract_init_properties_func: Function to extract init properties

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(file_path))
        base_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                base_class = node
                break
        if not base_class:
            return (False, f"Base class '{base_class_name}' not found")

        extract_from = config.get("extract_from", {})
        all_extracted_methods = set()
        all_extracted_props = set()
        for child_config in extract_from.values():
            all_extracted_methods.update(child_config.get("methods", []))
            all_extracted_props.update(child_config.get("properties", []))
            all_extracted_props.update(child_config.get("props", []))

        base_methods = set()
        for item in base_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                base_methods.add(item.name)

        base_props = set(extract_init_properties_func(base_class))
        missing_methods = all_extracted_methods - base_methods
        if missing_methods:
            return (False, f"Missing methods in base class: {missing_methods}")

        missing_props = all_extracted_props - base_props
        if missing_props:
            return (False, f"Missing properties in base class: {missing_props}")

        return (True, None)
    except Exception as e:
        return (False, f"Error during completeness validation: {str(e)}")


def validate_completeness_merge(
    file_path: Path,
    base_class_name: str,
    source_classes: List[str],
    original_props: Set[str],
    original_methods: Set[str],
    extract_init_properties_func,
) -> tuple[bool, Optional[str]]:
    """
    Validate that all original properties and methods are present after merge.

    Args:
        file_path: Path to modified file
        base_class_name: Name of merged class
        source_classes: List of source class names
        original_props: Set of original property names
        original_methods: Set of original method names
        extract_init_properties_func: Function to extract init properties

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(file_path))
        merged_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                merged_class = node
                break
        if not merged_class:
            return (False, f"Merged class '{base_class_name}' not found")

        new_props = set(extract_init_properties_func(merged_class))
        new_methods = set()
        for item in merged_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_methods.add(item.name)

        missing_props = original_props - new_props
        if missing_props:
            return (
                False,
                f"Missing properties after merge: {missing_props}. Original: {len(original_props)}, Found: {len(new_props)}",
            )

        special_methods = {"__init__", "__new__", "__del__"}
        regular_original = original_methods - special_methods
        regular_new = new_methods - special_methods
        missing_methods = regular_original - regular_new
        if missing_methods:
            return (
                False,
                f"Missing methods after merge: {missing_methods}. Original: {len(regular_original)}, Found: {len(regular_new)}",
            )

        return (True, None)
    except Exception as e:
        return (False, f"Error during completeness validation: {str(e)}")
