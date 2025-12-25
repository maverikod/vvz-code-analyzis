"""
Module merger.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from typing import Dict, List, Any, Optional

from .base import BaseRefactorer
from .formatters import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


class ClassMerger(BaseRefactorer):
    """Class for merging multiple classes into a single base class.

    This is the inverse operation of extract-superclass - it combines
    multiple classes into one base class."""

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate merge configuration."""
        from .validators import validate_merge_config as validate_config_func

        return validate_config_func(config, self.find_class)

    def merge_classes(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Merge multiple classes into a single base class.

        Args:
            config: Configuration dict with:
                - base_class: Name of the new merged class
                - source_classes: List of class names to merge
                - merge_methods: List of method names to merge (optional)
                - merge_props: List of property names to merge (optional)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            self.create_backup()
            self.load_file()
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                error_msg = format_error_message(
                    "config_validation", "; ".join(errors), self.file_path
                )
                return (False, error_msg)
            base_class_name = config.get("base_class")
            source_classes = config.get("source_classes", [])
            all_original_props = set()
            all_original_methods = set()
            source_nodes = []
            for src_class_name in source_classes:
                src_node = self.find_class(src_class_name)
                if not src_node:
                    return (False, f"Source class '{src_class_name}' not found")
                source_nodes.append(src_node)
                props = set(self.extract_init_properties(src_node))
                all_original_props.update(props)
                for item in src_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_original_methods.add(item.name)
            new_content = self._perform_merge(config, source_nodes)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            format_success, format_error = format_code_with_black(self.file_path)
            if not format_success:
                logger.warning(f"Code formatting failed (continuing): {format_error}")
            is_valid, error_msg = self.validate_python_syntax()
            if not is_valid:
                self.restore_backup()
                formatted_error = format_error_message(
                    "python_syntax", error_msg, self.file_path
                )
                return (False, formatted_error)
            is_complete, completeness_error = self.validate_completeness(
                base_class_name,
                source_classes,
                all_original_props,
                all_original_methods,
            )
            if not is_complete:
                self.restore_backup()
                formatted_error = format_error_message(
                    "completeness", completeness_error, self.file_path
                )
                return (False, formatted_error)
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                source_nodes, config
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
            return (True, "Class merge completed successfully")
        except Exception as e:
            if self.backup_path:
                self.restore_backup()
            return (False, f"Error during merge: {str(e)}")

    def _perform_merge(
        self, config: Dict[str, Any], source_nodes: List[ast.ClassDef]
    ) -> str:
        """Perform the actual class merging."""
        if not self.tree:
            raise ValueError("AST tree not loaded")
        base_class_name = config.get("base_class")
        merge_methods = config.get("merge_methods", [])
        merge_props = config.get("merge_props", [])
        merged_class_code = self._build_merged_class(
            base_class_name, source_nodes, merge_methods, merge_props
        )
        lines = self.original_content.split("\n")
        updated_lines = lines.copy()
        class_positions = {}
        for src_node in source_nodes:
            class_positions[src_node.name] = (
                src_node.lineno - 1,
                self._find_class_end(src_node, lines),
            )
        for src_name in sorted(class_positions.keys(), reverse=True):
            start, end = class_positions[src_name]
            del updated_lines[start:end]
        first_pos = min((pos[0] for pos in class_positions.values()))
        updated_lines.insert(first_pos, merged_class_code)
        return "\n".join(updated_lines)

    def _build_merged_class(
        self,
        base_class_name: str,
        source_nodes: List[ast.ClassDef],
        merge_methods: List[str],
        merge_props: List[str],
    ) -> str:
        """Build the merged class code."""
        lines = []
        lines.append(f"class {base_class_name}:")
        lines.append(
            '    """Merged class combining functionality from multiple classes."""'
        )
        lines.append("")
        all_props = set()
        for src_node in source_nodes:
            props = set(self.extract_init_properties(src_node))
            all_props.update(props)
        if all_props:
            lines.append("    def __init__(self):")
            for prop in sorted(all_props):
                lines.append(f"        self.{prop} = None")
            lines.append("")
        all_methods = {}
        for src_node in source_nodes:
            for item in src_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name not in all_methods:
                        all_methods[item.name] = item
        for method_name in sorted(all_methods.keys()):
            if merge_methods and method_name not in merge_methods:
                continue
            method_node = all_methods[method_name]
            method_code = self._extract_method_code(method_node, "    ")
            if method_code.strip():
                lines.append(method_code)
                lines.append("")
        return "\n".join(lines)

    def validate_completeness(
        self,
        base_class_name: str,
        source_classes: List[str],
        original_props: set,
        original_methods: set,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all original properties and methods are present.

        Uses pre-collected original_props and original_methods for strict
        validation against the merged class.
        """
        from .validators import (
            validate_completeness_merge as validate_completeness_func,
        )

        return validate_completeness_func(
            self.file_path,
            base_class_name,
            source_classes,
            original_props,
            original_methods,
            self.extract_init_properties,
        )

    def validate_docstrings(
        self, source_nodes: List[ast.ClassDef], config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all docstrings are preserved in merged class.

        Args:
            source_nodes: Original source class AST nodes
            config: Merge configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))
            base_class_name = config.get("base_class")
            merged_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                    merged_class = node
                    break
            if not merged_class:
                return (
                    False,
                    f"Merged class '{base_class_name}' not found after merge",
                )
            source_method_docstrings = {}
            for src_node in source_nodes:
                for item in src_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_docstring = ast.get_docstring(item)
                        if method_docstring:
                            if item.name not in source_method_docstrings:
                                source_method_docstrings[item.name] = method_docstring
            for method_name, expected_docstring in source_method_docstrings.items():
                merged_method = None
                for item in merged_class.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        merged_method = item
                        break
                if not merged_method:
                    return (
                        False,
                        f"Method '{method_name}' not found in merged class '{base_class_name}'",
                    )
                merged_method_docstring = ast.get_docstring(merged_method)
                if not merged_method_docstring:
                    return (
                        False,
                        f"Method '{method_name}' docstring missing in merged class '{base_class_name}'. Expected: {expected_docstring[:50]}...",
                    )
                if merged_method_docstring.strip() != expected_docstring.strip():
                    return (
                        False,
                        f"Method '{method_name}' docstring mismatch in merged class '{base_class_name}'. Expected: {expected_docstring[:50]}..., Got: {merged_method_docstring[:50]}...",
                    )
            return (True, None)
        except Exception as e:
            return (False, f"Error during docstring validation: {str(e)}")
