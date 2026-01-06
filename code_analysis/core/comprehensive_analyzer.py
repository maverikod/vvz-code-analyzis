"""
Comprehensive code analyzer combining multiple analysis types.

This module provides a unified interface for running multiple code analysis
checks that were previously done by code_mapper.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
import re
import tokenize
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ComprehensiveAnalyzer:
    """
    Comprehensive code analyzer combining multiple analysis types.

    Analyzes code for:
    - Placeholders (TODO, FIXME, etc.)
    - Stubs (pass, ellipsis, NotImplementedError)
    - Empty methods (excluding abstract)
    - Imports not at top of file
    - Long files
    - Code duplicates
    """

    def __init__(
        self,
        max_lines: int = 400,
        placeholder_patterns: Optional[List[str]] = None,
        ignore_abstract: bool = True,
    ) -> None:
        """
        Initialize comprehensive analyzer.

        Args:
            max_lines: Maximum lines threshold for long files.
            placeholder_patterns: Custom placeholder patterns (default: common patterns).
            ignore_abstract: Ignore abstract methods (default: True).
        """
        self.max_lines = max_lines
        self.ignore_abstract = ignore_abstract

        if placeholder_patterns is None:
            self.placeholder_patterns = [
                "TODO",
                "FIXME",
                "XXX",
                "HACK",
                "NOTE",
                "BUG",
                "OPTIMIZE",
                "PLACEHOLDER",
                "STUB",
                "NOT IMPLEMENTED",
            ]
        else:
            self.placeholder_patterns = placeholder_patterns

    def find_placeholders(
        self, file_path: Path, source_code: str
    ) -> List[Dict[str, Any]]:
        """
        Find placeholder patterns in code.

        Args:
            file_path: Path to file.
            source_code: Source code content.

        Returns:
            List of placeholder occurrences.
        """
        placeholders: List[Dict[str, Any]] = []
        lines = source_code.split("\n")

        # Pattern for matching placeholders (case-insensitive)
        pattern_str = "|".join(re.escape(p) for p in self.placeholder_patterns)
        pattern = re.compile(rf"\b({pattern_str})\b", re.IGNORECASE | re.MULTILINE)

        # Check comments
        try:
            tokens = list(tokenize.generate_tokens(StringIO(source_code).readline))
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    match = pattern.search(token.string)
                    if match:
                        line_num = token.start[0]
                        placeholders.append(
                            {
                                "line": line_num,
                                "type": "comment",
                                "pattern": match.group(1).upper(),
                                "text": token.string.strip(),
                                "context": (
                                    lines[line_num - 1]
                                    if line_num <= len(lines)
                                    else ""
                                ),
                            }
                        )
        except Exception as e:
            logger.debug(f"Error tokenizing {file_path}: {e}")

        # Check docstrings
        try:
            tree = ast.parse(source_code, filename=str(file_path))
            for node in ast.walk(tree):
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module),
                ):
                    docstring = ast.get_docstring(node, clean=False)
                    if docstring:
                        match = pattern.search(docstring)
                        if match:
                            line_num = node.lineno if hasattr(node, "lineno") else 1
                            placeholders.append(
                                {
                                    "line": line_num,
                                    "type": "docstring",
                                    "pattern": match.group(1).upper(),
                                    "text": docstring[:100],  # First 100 chars
                                    "context": (
                                        lines[line_num - 1]
                                        if line_num <= len(lines)
                                        else ""
                                    ),
                                }
                            )
        except SyntaxError:
            pass

        # Check string literals
        try:
            tree = ast.parse(source_code, filename=str(file_path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    match = pattern.search(node.value)
                    if match:
                        line_num = node.lineno if hasattr(node, "lineno") else 1
                        placeholders.append(
                            {
                                "line": line_num,
                                "type": "string",
                                "pattern": match.group(1).upper(),
                                "text": node.value[:100],
                                "context": (
                                    lines[line_num - 1]
                                    if line_num <= len(lines)
                                    else ""
                                ),
                            }
                        )
        except SyntaxError:
            pass

        return placeholders

    def find_stubs(self, file_path: Path, source_code: str) -> List[Dict[str, Any]]:
        """
        Find stub functions and methods.

        Args:
            file_path: Path to file.
            source_code: Source code content.

        Returns:
            List of stub occurrences.
        """
        stubs: List[Dict[str, Any]] = []

        try:
            tree = ast.parse(source_code, filename=str(file_path))
            lines = source_code.split("\n")

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Check if it's a method
                    is_method = False
                    class_name = None
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            if node in parent.body:
                                is_method = True
                                class_name = parent.name
                                break

                    # Check body
                    body = node.body
                    if not body:
                        continue

                    # Check for pass only
                    if len(body) == 1 and isinstance(body[0], ast.Pass):
                        stub_type = "pass"
                    # Check for ellipsis only
                    elif (
                        len(body) == 1
                        and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and body[0].value.value is Ellipsis
                    ):
                        stub_type = "ellipsis"
                    # Check for raise NotImplementedError only
                    elif (
                        len(body) == 1
                        and isinstance(body[0], ast.Raise)
                        and isinstance(body[0].exc, ast.Call)
                        and isinstance(body[0].exc.func, ast.Name)
                        and body[0].exc.func.id == "NotImplementedError"
                    ):
                        stub_type = "not_implemented"
                    # Check for return None only (if not abstract)
                    elif (
                        len(body) == 1
                        and isinstance(body[0], ast.Return)
                        and isinstance(body[0].value, ast.Constant)
                        and body[0].value.value is None
                    ):
                        # Check if abstract
                        is_abstract = any(
                            isinstance(d, ast.Name) and d.id == "abstractmethod"
                            for d in node.decorator_list
                        )
                        if not is_abstract:
                            stub_type = "return_none"
                        else:
                            continue
                    else:
                        continue

                    # Extract code snippet
                    start_line = node.lineno
                    end_line = getattr(node, "end_lineno", start_line) or start_line
                    code_snippet = "\n".join(lines[start_line - 1 : end_line])

                    stubs.append(
                        {
                            "function_name": node.name,
                            "class_name": class_name,
                            "line": start_line,
                            "type": "method" if is_method else "function",
                            "stub_type": stub_type,
                            "code_snippet": code_snippet,
                        }
                    )
        except SyntaxError:
            pass

        return stubs

    def find_empty_methods(
        self, file_path: Path, source_code: str
    ) -> List[Dict[str, Any]]:
        """
        Find empty methods (excluding abstract).

        Args:
            file_path: Path to file.
            source_code: Source code content.

        Returns:
            List of empty method occurrences.
        """
        empty_methods: List[Dict[str, Any]] = []

        try:
            tree = ast.parse(source_code, filename=str(file_path))
            lines = source_code.split("\n")

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class is abstract
                    is_abc = any(
                        isinstance(base, ast.Name) and base.id == "ABC"
                        for base in node.bases
                    )

                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            # Check if abstract
                            is_abstract = (
                                any(
                                    isinstance(d, ast.Name) and d.id == "abstractmethod"
                                    for d in item.decorator_list
                                )
                                or is_abc
                            )

                            if is_abstract and self.ignore_abstract:
                                continue

                            # Check body
                            body = item.body
                            if not body:
                                body_type = "empty"
                            elif len(body) == 1:
                                if isinstance(body[0], ast.Pass):
                                    body_type = "pass"
                                elif (
                                    isinstance(body[0], ast.Expr)
                                    and isinstance(body[0].value, ast.Constant)
                                    and body[0].value.value is Ellipsis
                                ):
                                    body_type = "ellipsis"
                                elif isinstance(body[0], ast.Expr):
                                    # Check if it's a docstring (string constant)
                                    if isinstance(
                                        body[0].value, ast.Constant
                                    ) and isinstance(body[0].value.value, str):
                                        # Only docstring (Python 3.8+)
                                        body_type = "docstring_only"
                                    elif isinstance(body[0].value, ast.Str):
                                        # Only docstring (Python < 3.8)
                                        body_type = "docstring_only"
                                    else:
                                        continue
                                else:
                                    continue
                            else:
                                continue

                            # Extract code snippet
                            start_line = item.lineno
                            end_line = (
                                getattr(item, "end_lineno", start_line) or start_line
                            )
                            code_snippet = "\n".join(lines[start_line - 1 : end_line])

                            empty_methods.append(
                                {
                                    "method_name": item.name,
                                    "class_name": node.name,
                                    "line": start_line,
                                    "body_type": body_type,
                                    "code_snippet": code_snippet,
                                    "is_abstract": is_abstract,
                                }
                            )
        except SyntaxError:
            pass

        return empty_methods

    def find_imports_not_at_top(
        self, file_path: Path, source_code: str
    ) -> List[Dict[str, Any]]:
        """
        Find imports that are not at the top of the file.

        Args:
            file_path: Path to file.
            source_code: Source code content.

        Returns:
            List of imports not at top.
        """
        imports_not_at_top: List[Dict[str, Any]] = []

        try:
            tree = ast.parse(source_code, filename=str(file_path))
            lines = source_code.split("\n")

            # Find first non-import, non-docstring statement
            first_non_import_line = None
            for stmt in tree.body:
                # Skip docstrings and imports
                if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                    continue
                if isinstance(stmt, ast.Expr):
                    # Check if it's a docstring
                    if isinstance(stmt.value, ast.Constant) and isinstance(
                        stmt.value.value, str
                    ):
                        continue
                    if isinstance(stmt.value, ast.Str):
                        continue
                first_non_import_line = stmt.lineno
                break

            # Check all imports at module level
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    import_line = node.lineno

                    # Skip if import is at top (before first non-import)
                    if first_non_import_line and import_line < first_non_import_line:
                        continue

                    # Get import details
                    if isinstance(node, ast.Import):
                        import_names = [alias.name for alias in node.names]
                        import_type = "import"
                        module = None
                    else:
                        import_names = [alias.name for alias in node.names]
                        import_type = "import_from"
                        module = node.module

                    for name in import_names:
                        imports_not_at_top.append(
                            {
                                "line": import_line,
                                "import_name": name,
                                "module": module,
                                "import_type": import_type,
                                "code_snippet": (
                                    lines[import_line - 1]
                                    if import_line <= len(lines)
                                    else ""
                                ),
                            }
                        )
        except SyntaxError:
            pass

        return imports_not_at_top

    def find_long_files(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Find files exceeding line limit.

        Args:
            files: List of file records with 'path' and 'lines' keys.

        Returns:
            List of long files.
        """
        long_files = []
        for file_record in files:
            lines = file_record.get("lines", 0)
            if lines > self.max_lines:
                long_files.append(
                    {
                        "path": file_record.get("path"),
                        "lines": lines,
                        "exceeds_by": lines - self.max_lines,
                    }
                )
        return sorted(long_files, key=lambda x: x["lines"], reverse=True)

    def check_flake8(self, file_path: Path) -> Dict[str, Any]:
        """
        Check file with flake8.

        Args:
            file_path: Path to file.

        Returns:
            Dictionary with flake8 results.
        """
        from ..core.code_quality import lint_with_flake8

        success, error_msg, errors = lint_with_flake8(file_path)

        return {
            "success": success,
            "error_message": error_msg,
            "errors": errors,
            "error_count": len(errors) if errors else 0,
        }

    def check_mypy(
        self, file_path: Path, config_file: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Check file with mypy.

        Args:
            file_path: Path to file.
            config_file: Optional path to mypy config file.

        Returns:
            Dictionary with mypy results.
        """
        from ..core.code_quality import type_check_with_mypy

        success, error_msg, errors = type_check_with_mypy(
            file_path, config_file, ignore_errors=False
        )

        return {
            "success": success,
            "error_message": error_msg,
            "errors": errors,
            "error_count": len(errors) if errors else 0,
        }
