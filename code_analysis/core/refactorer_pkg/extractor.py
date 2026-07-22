"""
Module extractor.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..database.files.update_standalone import index_file_via_driver
from .base import BaseRefactorer
from .extractor_ast import (
    build_base_class_ast,
    is_self_assignment_to_any,
    update_child_class_ast,
)
from .extractor_docstrings import validate_docstrings_preserved
from .extractor_perform import perform_extraction
from .formatters import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


class SuperclassExtractor(BaseRefactorer):
    """Class for extracting common functionality into base class."""

    def _build_base_class(
        self,
        base_class_name: str,
        child_nodes: List[Optional[ast.ClassDef]],
        extract_from: Dict[str, Dict[str, Any]],
        abstract_methods: List[str],
    ) -> str:
        """Compatibility wrapper for older tests. Returns base class source as string."""
        real_children = [c for c in child_nodes if c is not None]
        node = build_base_class_ast(
            base_class_name=base_class_name,
            child_nodes=real_children,
            extract_from=extract_from,
            abstract_methods=abstract_methods,
            find_method_in_class=self._find_method_in_class,
        )
        node = ast.fix_missing_locations(node)
        return ast.unparse(node)

    def _update_child_class(
        self,
        child_node: ast.ClassDef,
        base_class_name: str,
        child_config: Dict[str, Any],
        lines: List[str],
    ) -> str:
        """Compatibility wrapper for older tests. Returns updated child class code."""
        _ = lines
        node = update_child_class_ast(
            child_node,
            base_class_name,
            child_config,
            is_self_assign=is_self_assignment_to_any,
        )
        node = ast.fix_missing_locations(node)
        return ast.unparse(node)

    def get_class_bases(self, class_node: ast.ClassDef) -> List[str]:
        """Get list of base class names."""
        bases = []
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                parts = []
                node = base
                while isinstance(node, ast.Attribute):
                    parts.append(node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    parts.append(node.id)
                    bases.append(".".join(reversed(parts)))
        return bases

    def check_multiple_inheritance_conflicts(
        self, child_classes: List[str], base_class: Optional[str]
    ) -> tuple[bool, Optional[str]]:
        """Check for multiple inheritance conflicts."""
        if not self.tree:
            return (False, "AST tree not loaded")
        all_bases: Dict[str, List[str]] = {}
        for child_name in child_classes:
            child_node = self.find_class(child_name)
            if child_node:
                bases = self.get_class_bases(child_node)
                all_bases[child_name] = bases
        conflicts = []
        for child_name, bases in all_bases.items():
            if bases:
                conflicts.append(f"{child_name} already inherits from {bases}")
        if conflicts:
            return (False, f"Multiple inheritance conflicts: {'; '.join(conflicts)}")
        return (True, None)

    def check_method_compatibility(
        self, class_names: List[str], method_name: str
    ) -> tuple[bool, Optional[str]]:
        """Check if method has compatible signature across classes."""
        methods = []
        for class_name in class_names:
            class_node = self.find_class(class_name)
            if class_node:
                method = self._find_method_in_class(class_node, method_name)
                if method:
                    methods.append(method)
        if not methods:
            return (True, None)
        if len(methods) != len(class_names):
            return (False, f"Method {method_name} not found in all classes")
        first_method = methods[0]
        first_args = [arg.arg for arg in first_method.args.args]
        first_returns = self._get_return_type(first_method)
        for i, method in enumerate(methods[1:], 1):
            args = [arg.arg for arg in method.args.args]
            returns = self._get_return_type(method)
            if args != first_args:
                return (
                    False,
                    f"Method {method_name} has incompatible signatures in class {class_names[i]}",
                )
            if returns != first_returns:
                return (
                    False,
                    f"Method {method_name} has incompatible return types in class {class_names[i]}",
                )
        return (True, None)

    def _find_method_in_class(
        self, class_node: ast.ClassDef, method_name: str
    ) -> Optional[ast.FunctionDef]:
        """Find a method node in a class."""
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == method_name:
                    return item
        return None

    def _get_return_type(self, method_node: ast.FunctionDef) -> Optional[str]:
        """Extract return type annotation from method."""
        if method_node.returns:
            if isinstance(method_node.returns, ast.Name):
                return method_node.returns.id
        return None

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate extraction configuration."""
        from .validators import validate_extraction_config as validate_config_func

        return validate_config_func(config, self.find_class)

    def validate_completeness(
        self, base_class_name: str, child_classes: List[str], config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate that all members are present after extraction."""
        from .validators import (
            validate_completeness_extraction as validate_completeness_func,
        )

        return validate_completeness_func(
            self.file_path,
            base_class_name,
            child_classes,
            config,
            self.extract_init_properties,
        )

    def validate_docstrings(
        self, child_nodes: List[ast.ClassDef], config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate that all docstrings are preserved in base and child classes."""
        return validate_docstrings_preserved(str(self.file_path), child_nodes, config)

    def preview_extraction(
        self, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Preview extraction without making changes.

        Args:
            config: Extraction configuration

        Returns:
            Tuple of (success, error_message, preview_content)
        """
        try:
            self.load_file()
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                error_msg = format_error_message(
                    "config_validation", "; ".join(errors), self.file_path
                )
                return (False, error_msg, None)
            base_class_name = config.get("base_class")
            child_classes = config.get("child_classes", [])
            conflict_valid, conflict_error = self.check_multiple_inheritance_conflicts(
                child_classes, base_class_name
            )
            if not conflict_valid:
                return (False, conflict_error, None)
            child_nodes = []
            for child_name in child_classes:
                child_node = self.find_class(child_name)
                if not child_node:
                    return (False, f"Child class '{child_name}' not found", None)
                child_nodes.append(child_node)
            all_methods = set()
            extract_from = config.get("extract_from", {})
            for child_config in extract_from.values():
                all_methods.update(child_config.get("methods", []))
            for method_name in all_methods:
                is_compatible, error = self.check_method_compatibility(
                    child_classes, method_name
                )
                if not is_compatible:
                    return (False, error, None)
            new_content = perform_extraction(self, config, child_nodes)
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

    def extract_superclass(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Extract common functionality into base class."""
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
            child_classes = config.get("child_classes", [])
            conflict_valid, conflict_error = self.check_multiple_inheritance_conflicts(
                child_classes, base_class_name
            )
            if not conflict_valid:
                return (False, conflict_error)
            child_nodes = []
            for child_name in child_classes:
                child_node = self.find_class(child_name)
                if not child_node:
                    return (False, f"Child class '{child_name}' not found")
                child_nodes.append(child_node)
            config.get("abstract_methods", [])
            all_methods = set()
            extract_from = config.get("extract_from", {})
            for child_config in extract_from.values():
                all_methods.update(child_config.get("methods", []))
            for method_name in all_methods:
                is_compatible, error = self.check_method_compatibility(
                    child_classes, method_name
                )
                if not is_compatible:
                    return (False, error)
            new_content = perform_extraction(self, config, child_nodes)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Update database after file write
            if self.database and self.project_id and self.root_dir:
                try:
                    update_result = index_file_via_driver(
                        self.database,
                        file_path=str(self.file_path),
                        project_id=self.project_id,
                    )
                    if not update_result.get("success"):
                        logger.warning(
                            f"Failed to update database after superclass extraction: "
                            f"{update_result.get('error')}"
                        )
                    else:
                        logger.debug(
                            f"Database updated after superclass extraction: "
                            f"AST={update_result.get('ast_updated')}, "
                            f"CST={update_result.get('cst_updated')}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error updating database after superclass extraction: {e}",
                        exc_info=True,
                    )

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
                base_class_name, child_classes, config
            )
            if not is_complete:
                self.restore_backup()
                formatted_error = format_error_message(
                    "completeness", completeness_error, self.file_path
                )
                return (False, formatted_error)
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                child_nodes, config
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
            return (True, "Superclass extraction completed successfully")
        except Exception as e:
            if self.backup_path:
                self.restore_backup()
            return (False, f"Error during extraction: {str(e)}")

    def _build_base_class_ast(
        self,
        base_class_name: str,
        child_nodes: List[ast.ClassDef],
        extract_from: Dict[str, Dict[str, Any]],
        abstract_methods: List[str],
    ) -> ast.ClassDef:
        """Build the base class as AST node."""
        return build_base_class_ast(
            base_class_name=base_class_name,
            child_nodes=child_nodes,
            extract_from=extract_from,
            abstract_methods=abstract_methods,
            find_method_in_class=self._find_method_in_class,
        )

    def _update_child_class_ast(
        self,
        child_node: ast.ClassDef,
        base_class_name: str,
        child_config: Dict[str, Any],
    ) -> ast.ClassDef:
        """Update child class AST to inherit from base and remove extracted members."""
        return update_child_class_ast(
            child_node,
            base_class_name,
            child_config,
            is_self_assign=is_self_assignment_to_any,
        )
