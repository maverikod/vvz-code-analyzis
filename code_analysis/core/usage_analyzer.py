"""
Usage analyzer for finding method calls and attribute accesses.

This module analyzes AST to find where methods and properties are used.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path
from typing import Dict, Optional, Set, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class UsageAnalyzer:
    """Analyzer for finding method calls and attribute accesses in code."""

    def __init__(self, database=None) -> None:
        """Initialize usage analyzer."""
        self.database = database
        # Cache of defined methods and properties by class
        self._class_methods: Dict[str, Set[str]] = {}
        self._class_properties: Dict[str, Set[str]] = {}

    def analyze_file(self, file_path: Path, file_id: Optional[int] = None) -> None:
        """
        Analyze file for method calls and attribute accesses.

        Args:
            file_path: Path to Python file
            file_id: File ID in database
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))

            # First pass: collect defined methods and properties
            self._collect_definitions(tree)

            # Second pass: find usages
            self._find_usages(tree, file_path, file_id)

        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            logger.warning(f"Error analyzing file {file_path} for usages: {e}")

    def _collect_definitions(self, tree: ast.Module) -> None:
        """Collect all method and property definitions."""
        self._class_methods.clear()
        self._class_properties.clear()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                methods = set()
                properties = set()

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.add(item.name)
                        # Extract properties from __init__
                        if item.name == "__init__":
                            for stmt in item.body:
                                if isinstance(stmt, ast.Assign):
                                    for target in stmt.targets:
                                        if isinstance(target, ast.Attribute):
                                            if (
                                                isinstance(target.value, ast.Name)
                                                and target.value.id == "self"
                                            ):
                                                properties.add(target.attr)
                                elif isinstance(stmt, ast.AnnAssign):
                                    if isinstance(stmt.target, ast.Attribute):
                                        if (
                                            isinstance(stmt.target.value, ast.Name)
                                            and stmt.target.value.id == "self"
                                        ):
                                            properties.add(stmt.target.attr)

                if methods:
                    self._class_methods[class_name] = methods
                if properties:
                    self._class_properties[class_name] = properties

    def _find_usages(
        self, tree: ast.Module, file_path: Path, file_id: Optional[int]
    ) -> None:
        """Find all method calls and attribute accesses."""
        if not file_id:
            return

        visitor = UsageVisitor(
            self.database, file_id, self._class_methods, self._class_properties
        )
        visitor.visit(tree)


class UsageVisitor(ast.NodeVisitor):
    """AST visitor for finding method calls and attribute accesses."""

    def __init__(
        self,
        database,
        file_id: int,
        class_methods: Dict[str, Set[str]],
        class_properties: Dict[str, Set[str]],
    ) -> None:
        """Initialize usage visitor."""
        self.database = database
        self.file_id = file_id
        self.class_methods = class_methods
        self.class_properties = class_properties
        self.current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        old_class = self.current_class
        self.current_class = node.name
        # Visit children using generic_visit to maintain proper traversal
        self.generic_visit(node)
        self.current_class = old_class

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function/method call."""
        # Check if it's a method call (obj.method())
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            target_class = None

            # Try to determine the class of the object
            if isinstance(node.func.value, ast.Name):
                # Direct variable: var.method()
                var_name = node.func.value.id
                # Could be self, or a variable
                if var_name == "self" and self.current_class:
                    target_class = self.current_class
                # Check if method exists in known classes
                elif method_name in self.class_methods.get(
                    self.current_class or "", set()
                ):
                    target_class = self.current_class
            elif isinstance(node.func.value, ast.Attribute):
                # Chained: obj.attr.method()
                if isinstance(node.func.value.value, ast.Name):
                    if node.func.value.value.id == "self":
                        target_class = self.current_class

            # Save usage
            if self.database:
                try:
                    self.database.add_usage(
                        file_id=self.file_id,
                        line=node.lineno,
                        usage_type="method_call",
                        target_type="method",
                        target_name=method_name,
                        target_class=target_class,
                        context=self._get_context(node),
                    )
                except Exception as e:
                    logger.debug(f"Error adding usage: {e}")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Visit attribute access."""
        # Check if it's a property access (obj.property)
        if isinstance(node.value, ast.Name):
            var_name = node.value.id
            property_name = node.attr

            target_class = None
            if var_name == "self" and self.current_class:
                target_class = self.current_class
                # Check if it's a known property
                if property_name in self.class_properties.get(target_class, set()):
                    if self.database:
                        try:
                            self.database.add_usage(
                                file_id=self.file_id,
                                line=node.lineno,
                                usage_type="attribute_access",
                                target_type="property",
                                target_name=property_name,
                                target_class=target_class,
                                context=self._get_context(node),
                            )
                        except Exception as e:
                            logger.debug(f"Error adding property usage: {e}")

        self.generic_visit(node)

    def _get_context(self, node: ast.AST) -> Optional[str]:
        """Get context string for usage."""
        try:
            # Try to get parent function/class name
            parent = getattr(node, "parent", None)
            if parent:
                if isinstance(parent, ast.FunctionDef):
                    return f"{parent.name}()"
                elif isinstance(parent, ast.ClassDef):
                    return f"{parent.name}"

            # Fallback: get surrounding context from line
            return None
        except Exception:
            return None
