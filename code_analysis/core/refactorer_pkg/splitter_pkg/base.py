"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from ..utils import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


def extract_class_members(self, class_node: ast.ClassDef) -> Dict[str, List[Any]]:
    """Extract all properties and methods from class."""
    members: Dict[str, List[Any]] = {
        "properties": [],
        "methods": [],
        "nested_classes": [],
    }
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            members["methods"].append(item)
        elif isinstance(item, ast.ClassDef):
            members["nested_classes"].append(item)
    return members


def validate_split_config(
    self, src_class: ast.ClassDef, config: Dict[str, Any]
) -> tuple[bool, List[str]]:
    """Validate split configuration."""
    errors = []
    if not config.get("src_class"):
        errors.append("src_class not specified")
    all_properties = set(self.extract_init_properties(src_class))
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


def preview_split(
    self, config: Dict[str, Any]
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Preview split without making changes.

    Args:
        config: Split configuration

    Returns:
        Tuple of (success, error_message, preview_content)
    """
    try:
        self.load_file()
        src_class_name = config.get("src_class")
        if not src_class_name:
            return (False, "Source class name not specified in config", None)
        src_class = self.find_class(src_class_name)
        if not src_class:
            return (False, f"Class '{src_class_name}' not found in file", None)
        is_valid, errors = self.validate_split_config(src_class, config)
        if not is_valid:
            error_msg = format_error_message(
                "config_validation", "; ".join(errors), self.file_path
            )
            return (False, error_msg, None)
        new_content = self._perform_split(src_class, config)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(new_content)
        try:
            format_success, _ = format_code_with_black(tmp_path)
            if format_success:
                formatted_content = tmp_path.read_text()
            else:
                formatted_content = new_content
        finally:
            tmp_path.unlink()
        return (True, None, formatted_content)
    except Exception as e:
        error_msg = f"Error during preview: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return (False, error_msg, None)


def split_class(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Split class according to configuration."""
    try:
        self.create_backup()
        self.load_file()
        src_class_name = config.get("src_class")
        if not src_class_name:
            return (False, "Source class name not specified in config")
        src_class = self.find_class(src_class_name)
        if not src_class:
            return (False, f"Class '{src_class_name}' not found in file")
        original_props = set(self.extract_init_properties(src_class))
        original_methods = set()
        for item in src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                original_methods.add(item.name)
        is_valid, errors = self.validate_split_config(src_class, config)
        if not is_valid:
            error_msg = format_error_message(
                "config_validation", "; ".join(errors), self.file_path
            )
            return (False, error_msg)
        new_content = self._perform_split(src_class, config)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        format_success, format_error = format_code_with_black(self.file_path)
        if not format_success:
            logger.warning(f"Code formatting failed (continuing): {format_error}")
        is_valid, error_msg = self.validate_python_syntax()
        if not is_valid:
            self.restore_backup()
            return (False, f"Python validation failed: {error_msg}")
        is_complete, completeness_error = self.validate_completeness(
            src_class_name, config, original_props, original_methods
        )
        if not is_complete:
            self.restore_backup()
            formatted_error = format_error_message(
                "completeness", completeness_error, self.file_path
            )
            return (False, formatted_error)
        is_docstrings_valid, docstrings_error = self.validate_docstrings(
            src_class, config
        )
        if not is_docstrings_valid:
            self.restore_backup()
            formatted_error = format_error_message(
                "docstring", docstrings_error, self.file_path
            )
            return (False, formatted_error)
        try:
            import_valid, import_error = self.validate_imports()
            if not import_valid:
                logger.warning(f"Import validation warning: {import_error}")
        except Exception as e:
            logger.warning(f"Import validation skipped: {e}")
        return (True, "Split completed successfully")
    except Exception as e:
        if self.backup_path:
            self.restore_backup()
        return (False, f"Error during split: {str(e)}")
