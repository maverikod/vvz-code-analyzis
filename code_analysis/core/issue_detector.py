"""
Issue detector for the code mapper.

This module contains issue detection functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


class IssueDetector:
    """Issue detection functionality."""

    def __init__(
        self,
        issues: Dict[str, List[Any]],
        root_dir: Optional[Path] = None,
        database=None,
    ):
        """Initialize issue detector."""
        self.issues = issues
        self.root_dir = root_dir or Path(".")
        self.database = database
        self._stdlib_modules = (
            set(sys.stdlib_module_names)
            if hasattr(sys, "stdlib_module_names")
            else set()
        )

    def check_method_issues(
        self, node: ast.FunctionDef, file_path: str, class_name: Optional[str] = None
    ) -> None:
        """Check for method-specific issues."""
        # Check for Any type usage in parameters
        self._check_any_type_usage(node, file_path, class_name)
        # Check for generic Exception usage
        self._check_generic_exception_usage(node, file_path, class_name)

    def _check_any_type_usage(
        self, node: ast.FunctionDef, file_path: str, class_name: Optional[str] = None
    ) -> None:
        """Check for Any type usage in function parameters and return type."""
        # Check return type annotation
        if node.returns:
            if isinstance(node.returns, ast.Name) and node.returns.id == "Any":
                self.issues["any_type_usage"].append(
                    {
                        "file": file_path,
                        "class": class_name,
                        "method": node.name,
                        "type": "return_type",
                        "line": node.lineno,
                        "description": "Return type is Any",
                    }
                )
            elif isinstance(node.returns, ast.Attribute) and node.returns.attr == "Any":
                self.issues["any_type_usage"].append(
                    {
                        "file": file_path,
                        "class": class_name,
                        "method": node.name,
                        "type": "return_type",
                        "line": node.lineno,
                        "description": "Return type is Any",
                    }
                )

        # Check parameter type annotations
        for arg in node.args.args:
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name) and arg.annotation.id == "Any":
                    self.issues["any_type_usage"].append(
                        {
                            "file": file_path,
                            "class": class_name,
                            "method": node.name,
                            "type": "parameter",
                            "parameter": arg.arg,
                            "line": node.lineno,
                            "description": f"Parameter '{arg.arg}' has Any type",
                        }
                    )
                elif (
                    isinstance(arg.annotation, ast.Attribute)
                    and arg.annotation.attr == "Any"
                ):
                    self.issues["any_type_usage"].append(
                        {
                            "file": file_path,
                            "class": class_name,
                            "method": node.name,
                            "type": "parameter",
                            "parameter": arg.arg,
                            "line": node.lineno,
                            "description": f"Parameter '{arg.arg}' has Any type",
                        }
                    )

    def _check_generic_exception_usage(
        self, node: ast.FunctionDef, file_path: str, class_name: Optional[str] = None
    ) -> None:
        """Check for generic Exception usage in function body."""
        for stmt in node.body:
            self._check_statement_for_generic_exception(
                stmt, file_path, class_name, node.name
            )

    def _check_statement_for_generic_exception(
        self, stmt: ast.AST, file_path: str, class_name: Optional[str], method_name: str
    ) -> None:
        """Recursively check statement for generic Exception usage."""
        if isinstance(stmt, ast.Try):
            # Check except clauses
            for handler in stmt.handlers:
                if handler.type:
                    if (
                        isinstance(handler.type, ast.Name)
                        and handler.type.id == "Exception"
                    ):
                        self.issues["generic_exception_usage"].append(
                            {
                                "file": file_path,
                                "class": class_name,
                                "method": method_name,
                                "line": handler.lineno,
                                "type": "except_clause",
                                "description": (
                                    "Generic Exception caught "
                                    "without specific exception type"
                                ),
                            }
                        )
                    elif (
                        isinstance(handler.type, ast.Attribute)
                        and handler.type.attr == "Exception"
                    ):
                        self.issues["generic_exception_usage"].append(
                            {
                                "file": file_path,
                                "class": class_name,
                                "method": method_name,
                                "line": handler.lineno,
                                "type": "except_clause",
                                "description": (
                                    "Generic Exception caught "
                                    "without specific exception type"
                                ),
                            }
                        )
                else:
                    # Bare except clause
                    self.issues["generic_exception_usage"].append(
                        {
                            "file": file_path,
                            "class": class_name,
                            "method": method_name,
                            "line": handler.lineno,
                            "type": "bare_except",
                            "description": "Bare except clause without exception type",
                        }
                    )
            # Check for raise Exception within try block
            for stmt_in_try in stmt.body:
                self._check_statement_for_generic_exception(
                    stmt_in_try, file_path, class_name, method_name
                )
        elif isinstance(stmt, ast.Raise):
            # Check if raising generic Exception
            if stmt.exc:
                if isinstance(stmt.exc, ast.Name) and stmt.exc.id == "Exception":
                    self.issues["generic_exception_usage"].append(
                        {
                            "file": file_path,
                            "class": class_name,
                            "method": method_name,
                            "line": stmt.lineno,
                            "type": "raise_exception",
                            "description": (
                                "Raising generic Exception "
                                "instead of specific exception"
                            ),
                        }
                    )
                elif isinstance(stmt.exc, ast.Call):
                    if (
                        isinstance(stmt.exc.func, ast.Name)
                        and stmt.exc.func.id == "Exception"
                    ):
                        self.issues["generic_exception_usage"].append(
                            {
                                "file": file_path,
                                "class": class_name,
                                "method": method_name,
                                "line": stmt.lineno,
                                "type": "raise_exception",
                                "description": (
                                    "Raising generic Exception "
                                    "instead of specific exception"
                                ),
                            }
                        )

        # Recursively check nested statements
        if hasattr(stmt, "body") and isinstance(stmt.body, list):
            for nested_stmt in stmt.body:
                self._check_statement_for_generic_exception(
                    nested_stmt, file_path, class_name, method_name
                )

    def check_imports_in_middle(self, file_path: str, line_number: int) -> None:
        """Check for imports in the middle of files."""
        self.issues["imports_in_middle"].append(
            {
                "file": file_path,
                "line": line_number,
            }
        )

    def check_invalid_import(self, node: ast.Import, file_path: Path) -> None:
        """Check for invalid import statements."""
        for alias in node.names:
            module_name = alias.name.split(".")[0]  # Get top-level module name
            if not self._is_valid_module(module_name, file_path):
                self.issues["invalid_imports"].append(
                    {
                        "file": str(file_path),
                        "line": node.lineno,
                        "type": "import",
                        "module": alias.name,
                        "description": f"Module '{alias.name}' cannot be imported",
                    }
                )

    def check_invalid_import_from(self, node: ast.ImportFrom, file_path: Path) -> None:
        """Check for invalid import from statements."""
        if node.module is None:
            # Relative import without module name (e.g., "from . import something")
            if not self._is_valid_relative_import(
                node.level, None, file_path, node.names
            ):
                for alias in node.names:
                    self.issues["invalid_imports"].append(
                        {
                            "file": str(file_path),
                            "line": node.lineno,
                            "type": "import_from_relative",
                            "module": f"{'.' * node.level}{alias.name}",
                            "description": (
                                f"Relative import '{'.' * node.level}{alias.name}' "
                                "cannot be resolved"
                            ),
                        }
                    )
        elif node.level > 0:
            # Relative import with module name
            # (e.g., "from .module import something")
            if not self._is_valid_relative_import(node.level, node.module, file_path):
                for alias in node.names:
                    self.issues["invalid_imports"].append(
                        {
                            "file": str(file_path),
                            "line": node.lineno,
                            "type": "import_from_relative",
                            "module": f"{'.' * node.level}{node.module}",
                            "imported": alias.name,
                            "description": (
                                f"Relative import "
                                f"'{'.' * node.level}{node.module}' "
                                "cannot be resolved"
                            ),
                        }
                    )
        else:
            # Absolute import
            if not self._is_valid_module(node.module, file_path):
                for alias in node.names:
                    self.issues["invalid_imports"].append(
                        {
                            "file": str(file_path),
                            "line": node.lineno,
                            "type": "import_from",
                            "module": node.module,
                            "imported": alias.name,
                            "description": f"Module '{node.module}' cannot be imported",
                        }
                    )

    def _is_valid_module(self, module_name: str, file_path: Path) -> bool:
        """Check if a module can be imported."""
        # Check if it's a standard library module
        top_level = module_name.split(".")[0]
        if top_level in self._stdlib_modules:
            return True

        # Try to find the module using importlib.
        #
        # IMPORTANT: `importlib.util.find_spec("pkg.sub")` may import `pkg` to resolve
        # submodule search paths, which can cause side effects (e.g. server engine
        # registration logs) during static analysis. To avoid this, we only check
        # the top-level package when a dotted path is provided.
        try:
            spec = importlib.util.find_spec(top_level)
            if spec is not None and spec.origin is not None:
                return True
        except (ImportError, ValueError, ModuleNotFoundError):
            pass

        # Check if it's a local module in the project
        if self._is_local_module(module_name, file_path):
            return True

        return False

    def _is_local_module(self, module_name: str, file_path: Path) -> bool:
        """Check if module is a local module in the project."""
        parts = module_name.split(".")
        module_path = Path(*parts)

        search_roots = [self.root_dir, file_path.parent]
        for parent in file_path.parent.parents:
            if parent == self.root_dir.parent:
                break
            search_roots.append(parent)

        return any(
            self._module_path_exists(root / module_path) for root in search_roots
        )

    def _resolve_relative_base(self, level: int, file_path: Path) -> Optional[Path]:
        """Resolve the base directory for a relative import."""
        if level <= 0:
            return file_path.parent

        target_dir = file_path.parent
        for _ in range(level - 1):
            target_dir = target_dir.parent
            if target_dir == self.root_dir.parent or not target_dir.exists():
                return None

        if not target_dir.exists() or not str(target_dir).startswith(
            str(self.root_dir)
        ):
            return None

        return target_dir

    def _module_path_exists(self, base_path: Path) -> bool:
        """Check if a module path exists either as file or package."""
        return (
            base_path.with_suffix(".py").exists()
            or (base_path / "__init__.py").exists()
        )

    def _is_valid_relative_import(
        self,
        level: int,
        module_name: Optional[str],
        file_path: Path,
        imported_names: Optional[List[ast.alias]] = None,
    ) -> bool:
        """Check if a relative import can be resolved."""
        base_dir = self._resolve_relative_base(level, file_path)
        if base_dir is None:
            return False

        if module_name:
            module_path = base_dir / module_name.replace(".", "/")
            return self._module_path_exists(module_path)

        if imported_names:
            for alias in imported_names:
                alias_path = base_dir / alias.name.replace(".", "/")
                if not self._module_path_exists(alias_path):
                    return False

        return True
