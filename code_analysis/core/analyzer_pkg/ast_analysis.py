"""
Module ast_analysis.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _analyze_ast(
    self, tree: ast.Module, file_path: Path, file_id: Optional[int] = None
) -> None:
    """Analyze AST nodes."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            self._analyze_class(node, file_path, file_id)
        elif isinstance(node, ast.FunctionDef):
            # Only analyze top-level functions (not methods)
            # Methods are handled in _analyze_class
            # Skip methods here - they will be handled in _analyze_class
            pass
        elif isinstance(node, ast.Import):
            self._analyze_import(node, file_path, file_id)
        elif isinstance(node, ast.ImportFrom):
            self._analyze_import_from(node, file_path, file_id)

    # Second pass: analyze classes and top-level functions
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            self._analyze_class(node, file_path, file_id)
        elif isinstance(node, ast.FunctionDef):
            self._analyze_function(node, file_path, file_id)


def _analyze_class(
    self, node: ast.ClassDef, file_path: Path, file_id: Optional[int] = None
) -> None:
    """Analyze class definition."""
    class_name = node.name
    file_path_str = str(file_path)
    bases = [
        base.id if isinstance(base, ast.Name) else str(base) for base in node.bases
    ]
    docstring = ast.get_docstring(node)

    class_info: Dict[str, Any] = {
        "name": class_name,
        "file": file_path_str,
        "line": node.lineno,
        "bases": bases,
        "methods": [],
        "docstring": docstring,
    }

    # Save to database
    class_id = None
    if self.database and file_id:
        class_id = self.database.add_class(
            file_id, class_name, node.lineno, docstring, bases
        )

        # Save class content for full-text search
        try:
            class_code = (
                ast.get_source_segment(self._get_file_content(file_path), node) or ""
            )
            self.database.add_code_content(
                file_id=file_id,
                entity_type="class",
                entity_name=class_name,
                content=class_code,
                docstring=docstring,
                entity_id=class_id,
            )
        except Exception as e:
            logger.debug(f"Error saving class content: {e}")

    # Check for class docstring
    if not docstring:
        issue_data = {
            "class": class_name,
            "file": file_path_str,
            "line": node.lineno,
        }
        self.issues["classes_without_docstrings"].append(issue_data)
        if self.database and class_id:
            self.database.add_issue(
                "classes_without_docstrings",
                f"Class '{class_name}' missing docstring",
                line=node.lineno,
                file_id=file_id,
                class_id=class_id,
                metadata=issue_data,
            )

    # Analyze methods
    for method in node.body:
        if isinstance(method, ast.FunctionDef):
            self._analyze_method(method, file_path, class_name, class_id, file_id)
            class_info["methods"].append(method.name)

    self.code_map["classes"][f"{file_path}:{class_name}"] = class_info


def _analyze_function(
    self, node: ast.FunctionDef, file_path: Path, file_id: Optional[int] = None
) -> None:
    """Analyze function definition."""
    file_path_str = str(file_path)
    args = [arg.arg for arg in node.args.args]
    docstring = ast.get_docstring(node)

    func_info = {
        "name": node.name,
        "file": file_path_str,
        "line": node.lineno,
        "args": args,
        "docstring": docstring,
    }

    # Save to database
    function_id = None
    if self.database and file_id:
        function_id = self.database.add_function(
            file_id, node.name, node.lineno, args, docstring
        )

        # Save function content for full-text search
        try:
            function_code = (
                ast.get_source_segment(self._get_file_content(file_path), node) or ""
            )
            self.database.add_code_content(
                file_id=file_id,
                entity_type="function",
                entity_name=node.name,
                content=function_code,
                docstring=docstring,
                entity_id=function_id,
            )
        except Exception as e:
            logger.debug(f"Error saving function content: {e}")

    # Check for function docstring
    if not docstring:
        issue_data = {
            "class": None,
            "file": file_path_str,
            "line": node.lineno,
            "method": node.name,
        }
        self.issues["methods_without_docstrings"].append(issue_data)
        if self.database and function_id:
            self.database.add_issue(
                "methods_without_docstrings",
                f"Function '{node.name}' missing docstring",
                line=node.lineno,
                file_id=file_id,
                function_id=function_id,
                metadata=issue_data,
            )

    self.code_map["functions"][f"{file_path}:{node.name}"] = func_info


def _analyze_method(
    self,
    node: ast.FunctionDef,
    file_path: Path,
    class_name: str,
    class_id: Optional[int] = None,
    file_id: Optional[int] = None,
) -> None:
    """Analyze method definition."""
    file_path_str = str(file_path)
    args = [arg.arg for arg in node.args.args]
    docstring = ast.get_docstring(node)
    is_abstract = self._is_abstract_method(node)
    has_pass = self._has_pass_statement(node)
    has_not_implemented = self._has_not_implemented_error(node)

    # Save to database
    method_id = None
    if self.database and class_id:
        method_id = self.database.add_method(
            class_id,
            node.name,
            node.lineno,
            args,
            docstring,
            is_abstract,
            has_pass,
            has_not_implemented,
        )

        # Save method content for full-text search
        try:
            method_code = (
                ast.get_source_segment(self._get_file_content(file_path), node) or ""
            )
            file_id = self.database.get_file_id(str(file_path))
            if file_id:
                self.database.add_code_content(
                    file_id=file_id,
                    entity_type="method",
                    entity_name=f"{class_name}.{node.name}",
                    content=method_code,
                    docstring=docstring,
                    entity_id=method_id,
                )
        except Exception as e:
            logger.debug(f"Error saving method content: {e}")

    # Check for method docstring
    if not docstring:
        issue_data = {
            "class": class_name,
            "file": file_path_str,
            "line": node.lineno,
            "method": node.name,
        }
        self.issues["methods_without_docstrings"].append(issue_data)
        if self.database and method_id:
            self.database.add_issue(
                "methods_without_docstrings",
                f"Method '{class_name}.{node.name}' missing docstring",
                line=node.lineno,
                file_id=file_id,
                class_id=class_id,
                method_id=method_id,
                metadata=issue_data,
            )

    # Check for pass statements
    if has_pass:
        issue_data = {
            "class": class_name,
            "file": file_path_str,
            "line": node.lineno,
            "method": node.name,
        }
        self.issues["methods_with_pass"].append(issue_data)
        if self.database and method_id:
            self.database.add_issue(
                "methods_with_pass",
                f"Method '{class_name}.{node.name}' contains only pass statement",
                line=node.lineno,
                file_id=file_id,
                class_id=class_id,
                method_id=method_id,
                metadata=issue_data,
            )

    # Check for NotImplementedError in non-abstract methods
    if has_not_implemented and not is_abstract:
        issue_data = {
            "class": class_name,
            "file": file_path_str,
            "line": node.lineno,
            "method": node.name,
        }
        self.issues["not_implemented_in_non_abstract"].append(issue_data)
        if self.database and method_id:
            self.database.add_issue(
                "not_implemented_in_non_abstract",
                (
                    f"Method '{class_name}.{node.name}' "
                    "raises NotImplementedError but is not abstract"
                ),
                line=node.lineno,
                file_id=file_id,
                class_id=class_id,
                method_id=method_id,
                metadata=issue_data,
            )
