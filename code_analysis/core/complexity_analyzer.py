"""
Cyclomatic complexity analyzer for Python code.

This module provides functionality to calculate cyclomatic complexity
for functions, methods, and classes using AST analysis.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Dict, List, Optional, Union


class ComplexityAnalyzer(ast.NodeVisitor):
    """
    AST visitor to calculate cyclomatic complexity.

    Cyclomatic complexity measures the number of linearly independent paths
    through a program's source code. It is calculated as:
    Complexity = 1 + number of decision points

    Decision points include:
    - if, elif, else statements
    - for, while loops
    - try, except, finally blocks
    - and, or operators in conditions
    - case/match statements (Python 3.10+)

    Attributes:
        complexity: Current complexity score
    """

    def __init__(self) -> None:
        """Initialize complexity analyzer."""
        self.complexity = 1  # Base complexity is 1

    def visit_If(self, node: ast.If) -> None:
        """Visit if statement - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Visit for loop - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        """Visit while loop - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        """Visit try block - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Visit except handler - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Visit with statement - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """Visit boolean operator (and/or) - adds complexity based on number of operands."""
        # For 'and' or 'or', each additional operand adds a decision point
        # If we have: a and b and c, that's 2 decision points (a->b, b->c)
        if isinstance(node.op, (ast.And, ast.Or)):
            self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        """Visit ternary expression - adds 1 to complexity."""
        self.complexity += 1
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        """Visit match statement (Python 3.10+) - adds complexity based on number of cases."""
        # Each case in match statement adds 1 to complexity
        self.complexity += len(node.cases)
        self.generic_visit(node)


def calculate_complexity(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> int:
    """
    Calculate cyclomatic complexity for a function or method.

    Args:
        node: AST node representing a function or method definition.

    Returns:
        Cyclomatic complexity score (minimum is 1).

    Examples:
        >>> import ast
        >>> code = "def simple(): return 1"
        >>> tree = ast.parse(code)
        >>> func = tree.body[0]
        >>> calculate_complexity(func)
        1

        >>> code = "def complex_func(x):\\n    if x > 0:\\n        return 1\\n    else:\\n        return 0"
        >>> tree = ast.parse(code)
        >>> func = tree.body[0]
        >>> calculate_complexity(func)
        2
    """
    analyzer = ComplexityAnalyzer()
    analyzer.visit(node)
    return analyzer.complexity


class _FunctionCollector(ast.NodeVisitor):
    """AST visitor to collect functions and methods with their parent classes."""

    def __init__(self) -> None:
        """Initialize collector."""
        self.functions: List[
            tuple[Union[ast.FunctionDef, ast.AsyncFunctionDef], Optional[str]]
        ] = []
        self._current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition - track current class name."""
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        self.functions.append((node, self._current_class))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition."""
        self.functions.append((node, self._current_class))
        self.generic_visit(node)


def analyze_file_complexity(
    file_path: str, source_code: Optional[str] = None
) -> Dict[str, List[Dict[str, Union[str, int]]]]:
    """
    Analyze complexity for all functions and methods in a file.

    Args:
        file_path: Path to Python file.
        source_code: Optional source code content. If not provided, file is read.

    Returns:
        Dictionary with keys:
            - functions: List of function complexity results
            - methods: List of method complexity results
        Each result contains:
            - name: Function/method name
            - line: Line number
            - complexity: Complexity score
            - type: "function" or "method"

    Raises:
        SyntaxError: If file contains invalid Python syntax.
        FileNotFoundError: If file_path doesn't exist and source_code is not provided.
    """
    if source_code is None:
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()

    tree = ast.parse(source_code, filename=file_path)

    collector = _FunctionCollector()
    collector.visit(tree)

    functions: List[Dict[str, Union[str, int]]] = []
    methods: List[Dict[str, Union[str, int]]] = []

    for node, class_name in collector.functions:
        complexity = calculate_complexity(node)
        is_method = class_name is not None

        result = {
            "name": node.name,
            "line": node.lineno,
            "complexity": complexity,
            "type": "method" if is_method else "function",
        }

        if is_method:
            result["class_name"] = class_name
            methods.append(result)
        else:
            functions.append(result)

    return {"functions": functions, "methods": methods}


def analyze_function_complexity(
    source_code: str, function_name: Optional[str] = None
) -> Optional[Dict[str, Union[str, int]]]:
    """
    Analyze complexity for a specific function in source code.

    Args:
        source_code: Python source code.
        function_name: Optional function name to analyze. If None, analyzes first function.

    Returns:
        Dictionary with function complexity information, or None if function not found.
    """
    tree = ast.parse(source_code)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if function_name is None or node.name == function_name:
                complexity = calculate_complexity(node)
                return {
                    "name": node.name,
                    "line": node.lineno,
                    "complexity": complexity,
                    "type": "function",
                }

    return None
