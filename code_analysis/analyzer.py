"""
Code analyzer for the code mapper.

This module contains the core analysis functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path
import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Core code analyzer functionality."""

    def __init__(
        self,
        root_dir: str = ".",
        output_dir: str = "code_analysis",
        max_lines: int = 400,
        issue_detector=None,
        database=None,
    ):
        """Initialize code analyzer."""
        self.root_dir = Path(root_dir)
        self.output_dir = Path(output_dir)
        self.max_lines = max_lines
        self.issue_detector = issue_detector
        self.database = database

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True)

        # Keep code_map for backward compatibility (YAML mode)
        self.code_map: Dict[str, Any] = {
            "files": {},
            "classes": {},
            "functions": {},
            "imports": {},
            "dependencies": {},
        }
        # Issues tracking (for backward compatibility)
        self.issues: Dict[str, List[Any]] = {
            "methods_with_pass": [],
            "not_implemented_in_non_abstract": [],
            "methods_without_docstrings": [],
            "files_without_docstrings": [],
            "classes_without_docstrings": [],
            "files_too_large": [],
            "any_type_usage": [],
            "generic_exception_usage": [],
            "imports_in_middle": [],
            "invalid_imports": [],
        }

    def analyze_file(self, file_path: Path) -> None:
        """Analyze a single Python file."""
        try:
            file_path_str = str(file_path)
            file_stat = file_path.stat()
            last_modified = file_stat.st_mtime

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # Check file size
            lines = content.split("\n")
            line_count = len(lines)
            has_docstring = self._has_file_docstring(tree)

            # Save file to database if using SQLite
            file_id = None
            if self.database:
                file_id = self.database.add_file(
                    file_path_str, line_count, last_modified, has_docstring
                )
                # Clear old data for this file
                self.database.clear_file_data(file_id)

            # Check file size
            if line_count > self.max_lines:
                issue_data = {
                    "file": file_path_str,
                    "lines": line_count,
                    "limit": self.max_lines,
                    "exceeds_limit": line_count - self.max_lines,
                }
                self.issues["files_too_large"].append(issue_data)

                if self.database and file_id:
                    self.database.add_issue(
                        "files_too_large",
                        f"File exceeds line limit: {line_count} > {self.max_lines}",
                        line=None,
                        file_id=file_id,
                        metadata=issue_data,
                    )

            # Check for file docstring
            if not has_docstring:
                self.issues["files_without_docstrings"].append(file_path_str)
                if self.database and file_id:
                    self.database.add_issue(
                        "files_without_docstrings",
                        "File missing docstring",
                        line=None,
                        file_id=file_id,
                    )

            # Analyze AST
            self._analyze_ast(tree, file_path, file_id)

        except (OSError, IOError, ValueError, SyntaxError, UnicodeDecodeError) as e:
            logger.error(f"Error analyzing file {file_path}: {e}")

    def _has_file_docstring(self, tree: ast.Module) -> bool:
        """Check if file has a docstring."""
        if not tree.body:
            return False

        first_node = tree.body[0]
        return (
            isinstance(first_node, ast.Expr)
            and isinstance(first_node.value, ast.Constant)
            and isinstance(first_node.value.value, str)
        )

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

    def _has_pass_statement(self, node: ast.FunctionDef) -> bool:
        """Check if function has only pass statement."""
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            return True
        return False

    def _has_not_implemented_error(self, node: ast.FunctionDef) -> bool:
        """Check if function raises NotImplementedError."""
        for stmt in node.body:
            if isinstance(stmt, ast.Raise):
                if isinstance(stmt.exc, ast.Call):
                    if (
                        isinstance(stmt.exc.func, ast.Name)
                        and stmt.exc.func.id == "NotImplementedError"
                    ):
                        return True
        return False

    def _is_abstract_method(self, node: ast.FunctionDef) -> bool:
        """Check if method is abstract."""
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                return True
        return False

    def _analyze_import(
        self, node: ast.Import, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze import statement."""
        file_path_str = str(file_path)
        for alias in node.names:
            import_key = f"{file_path}:{alias.name}"
            import_info = {
                "name": alias.name,
                "file": file_path_str,
                "line": node.lineno,
                "type": "import",
            }
            self.code_map["imports"][import_key] = import_info

            # Save to database
            if self.database and file_id:
                self.database.add_import(
                    file_id, alias.name, None, "import", node.lineno
                )

        # Check for invalid imports
        if self.issue_detector:
            self.issue_detector.check_invalid_import(node, file_path)

    def _analyze_import_from(
        self, node: ast.ImportFrom, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze import from statement."""
        file_path_str = str(file_path)
        module = node.module or ""
        for alias in node.names:
            import_key = f"{file_path}:{alias.name}"
            import_info = {
                "name": alias.name,
                "file": file_path_str,
                "line": node.lineno,
                "type": "import_from",
                "module": module,
            }
            self.code_map["imports"][import_key] = import_info

            # Save to database
            if self.database and file_id:
                self.database.add_import(
                    file_id, alias.name, module, "import_from", node.lineno
                )

        # Check for invalid imports
        if self.issue_detector:
            self.issue_detector.check_invalid_import_from(node, file_path)
