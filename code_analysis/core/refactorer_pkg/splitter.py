"""
Module splitter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

from .base import BaseRefactorer
from .formatters import format_code_with_black, format_error_message
from .splitter_ast import (
    build_modified_source_class_ast,
    build_new_class_ast,
)
from .splitter_docstrings import validate_docstrings_impl
from .splitter_source import (
    build_modified_source_class,
    create_method_wrapper_impl,
)

logger = logging.getLogger(__name__)


class ClassSplitter(BaseRefactorer):
    """Class for splitting classes into smaller components."""

    def _build_new_class_code(
        self,
        dst_class_name: str,
        src_class: ast.ClassDef,
        dst_config: Dict[str, Any],
        base_indent: int = 0,
    ) -> str:
        """
        Build destination class as source code string.

        This path is used to preserve original formatting and comments by slicing
        method bodies from the original source.
        """
        class_indent = " " * base_indent
        indent = class_indent + "    "
        lines: list[str] = [f"{class_indent}class {dst_class_name}:"]

        docstring = ast.get_docstring(src_class)
        if docstring:
            lines.append(f'{indent}"""{docstring}"""')

        props = dst_config.get("props", []) or []
        if props:
            lines.append(f"{indent}def __init__(self):")
            init_indent = indent + "    "
            for prop in props:
                lines.append(f"{init_indent}self.{prop} = None")

        methods = dst_config.get("methods", []) or []
        for method_name in methods:
            method_node = self._find_method_in_class(src_class, method_name)
            if not method_node:
                logger.warning(
                    f"Method {method_name} not found in source class for destination class {dst_class_name}"
                )
                continue
            method_code = self._extract_method_code(method_node, indent)
            if method_code.strip():
                lines.append(method_code)

        if len(lines) == 1:
            lines.append(f"{indent}pass")
        return "\n".join(lines)

    def _build_new_class(
        self,
        dst_class_name: str,
        src_class: ast.ClassDef,
        dst_config: Dict[str, Any],
        base_indent: int = 0,
    ) -> str:
        """Compatibility wrapper: build AST then unparse to string for tests."""
        _ = base_indent
        node = build_new_class_ast(
            dst_class_name,
            src_class,
            dst_config,
            self._find_method_in_class,
        )
        node = ast.fix_missing_locations(node)
        return ast.unparse(node)

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
        from .validators import validate_split_config as validate_config_func

        return validate_config_func(src_class, config, self.extract_init_properties)

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

            # Update database after file write
            if self.database and self.project_id and self.root_dir:
                try:
                    update_result = self.database.index_file(
                        file_path=str(self.file_path),
                        project_id=self.project_id,
                    )
                    if not update_result.get("success"):
                        logger.warning(
                            f"Failed to update database after class split: "
                            f"{update_result.get('error')}"
                        )
                    else:
                        logger.debug(
                            f"Database updated after class split: "
                            f"AST={update_result.get('ast_updated')}, "
                            f"CST={update_result.get('cst_updated')}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error updating database after class split: {e}",
                        exc_info=True,
                    )

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

    def _perform_split(self, src_class: ast.ClassDef, config: Dict[str, Any]) -> str:
        """
        Perform the actual class splitting using source slicing.

        We intentionally avoid `ast.unparse` here because it drops comments.
        """
        if not self.tree:
            raise ValueError("AST tree not loaded")
        dst_classes = config.get("dst_classes", {})
        method_mapping: Dict[str, str] = {}
        prop_mapping: Dict[str, str] = {}
        for dst_class_name, dst_config in dst_classes.items():
            for method in dst_config.get("methods", []):
                method_mapping[method] = dst_class_name
            for prop in dst_config.get("props", []):
                prop_mapping[prop] = dst_class_name
        if not hasattr(src_class, "lineno"):
            raise ValueError("Source class has no source location information")
        lines = self.original_content.split("\n")
        start = src_class.lineno - 1
        end = (
            src_class.end_lineno
            if hasattr(src_class, "end_lineno") and src_class.end_lineno
            else self._find_class_end(src_class, lines)
        )
        before = "\n".join(lines[:start]).rstrip("\n")
        after = "\n".join(lines[end:]).lstrip("\n")

        modified_src = self._build_modified_source_class(
            src_class, method_mapping, prop_mapping, dst_classes, base_indent=0
        )
        new_classes: list[str] = []
        for dst_class_name, dst_config in dst_classes.items():
            new_classes.append(
                self._build_new_class_code(
                    dst_class_name, src_class, dst_config, base_indent=0
                )
            )

        parts: list[str] = []
        if before.strip():
            parts.append(before)
        parts.append(modified_src)
        parts.extend(new_classes)
        if after.strip():
            parts.append(after)

        return "\n\n".join(parts).rstrip() + "\n"

    def _get_indent(self, line: str) -> int:
        """Get indentation level of a line."""
        return len(line) - len(line.lstrip())

    def _build_new_class_ast(
        self, dst_class_name: str, src_class: ast.ClassDef, dst_config: Dict[str, Any]
    ) -> ast.ClassDef:
        """Build AST node for a new destination class."""
        return build_new_class_ast(
            dst_class_name,
            src_class,
            dst_config,
            self._find_method_in_class,
        )

    def _build_modified_source_class_ast(
        self,
        src_class: ast.ClassDef,
        method_mapping: Dict[str, str],
        prop_mapping: Dict[str, str],
        dst_classes: Dict[str, Dict[str, Any]],
    ) -> ast.ClassDef:
        """Build modified source class AST with wrappers and property references."""
        return build_modified_source_class_ast(
            src_class,
            method_mapping,
            prop_mapping,
            dst_classes,
            self.extract_init_properties,
            self._find_method_in_class,
        )

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

    def _build_modified_source_class(
        self,
        src_class: ast.ClassDef,
        method_mapping: Dict[str, str],
        prop_mapping: Dict[str, str],
        dst_classes: Dict[str, Dict[str, Any]],
        base_indent: int,
    ) -> str:
        """Build modified source class with wrappers and property references."""
        return build_modified_source_class(
            src_class,
            method_mapping,
            prop_mapping,
            dst_classes,
            base_indent,
            self.original_content,
            self.extract_init_properties,
            self._find_method_in_class,
            self._extract_method_code,
            self._create_method_wrapper,
        )

    def _create_method_wrapper(
        self, method_name: str, dst_class_name: str, indent: str
    ) -> str:
        """Create a wrapper method that delegates to the destination class."""
        return create_method_wrapper_impl(
            self.tree, method_name, dst_class_name, indent
        )

    def validate_completeness(
        self,
        src_class_name: str,
        config: Dict[str, Any],
        original_props: set,
        original_methods: set,
    ) -> tuple[bool, Optional[str]]:
        """Validate that all original properties and methods are present."""
        from .validators import (
            validate_completeness_split as validate_completeness_func,
        )

        return validate_completeness_func(
            self.file_path,
            src_class_name,
            config,
            original_props,
            original_methods,
            self.extract_init_properties,
        )

    def validate_docstrings(
        self, src_class: ast.ClassDef, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate that all docstrings are preserved in destination classes."""
        return validate_docstrings_impl(self.file_path, src_class, config)
