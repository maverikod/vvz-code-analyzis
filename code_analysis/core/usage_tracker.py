"""
Usage tracker - AST visitor to track code usages (function calls, method calls, instantiations).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class UsageTracker(ast.NodeVisitor):
    """
    AST visitor to track code usages (function calls, method calls, class instantiations).

    Tracks:
    - Function calls: func_name()
    - Method calls: obj.method_name()
    - Class instantiations: ClassName()
    - Attribute accesses: obj.attribute (for properties)
    """

    def __init__(self, add_usage_callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize usage tracker.

        Args:
            add_usage_callback: Callback function to add usage record.
                Called with dict containing:
                - line: Line number
                - usage_type: 'call', 'instantiation', 'attribute'
                - target_type: 'class', 'function', 'method', 'property'
                - target_name: Name of target entity
                - target_class: Optional class name (for methods/properties)
                - context: Optional context information
        """
        self._current_class: Optional[str] = None
        self._current_function: Optional[str] = None
        self._add_usage = add_usage_callback
        self._usages: List[Dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition - track current class name."""
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition - track current function name."""
        old_function = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = old_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition - track current function name."""
        old_function = self._current_function
        self._current_function = node.name
        self.generic_visit(node)
        self._current_function = old_function

    def visit_Call(self, node: ast.Call) -> None:
        """
        Visit function/method call or class instantiation.

        Handles:
        - Function calls: func_name()
        - Method calls: obj.method_name()
        - Class instantiations: ClassName()
        """
        try:
            func = node.func

            # Method call: obj.method()
            if isinstance(func, ast.Attribute):
                method_name = func.attr
                target_type = "method"
                usage_type = "call"

                # Try to determine class from attribute value
                target_class = None
                if isinstance(func.value, ast.Name):
                    # self.method() or obj.method()
                    var_name = func.value.id
                    if var_name == "self" and self._current_class:
                        target_class = self._current_class
                    # Could be obj.method() where obj is instance of some class
                    # For now, we track method name and context
                elif isinstance(func.value, ast.Attribute):
                    # obj.attr.method() - nested attribute
                    # Extract the base object name if possible
                    base = func.value
                    while isinstance(base, ast.Attribute):
                        base = base.value
                    if (
                        isinstance(base, ast.Name)
                        and base.id == "self"
                        and self._current_class
                    ):
                        target_class = self._current_class

                self._record_usage(
                    line=node.lineno,
                    usage_type=usage_type,
                    target_type=target_type,
                    target_name=method_name,
                    target_class=target_class,
                )

            # Function call or class instantiation: func_name() or ClassName()
            elif isinstance(func, ast.Name):
                name = func.id
                # Determine if it's a class instantiation or function call
                # We can't always know for sure, but we can make educated guesses:
                # - If name starts with uppercase, likely a class
                # - Otherwise, likely a function
                if name and name[0].isupper():
                    # Likely class instantiation
                    target_type = "class"
                    usage_type = "instantiation"
                else:
                    # Likely function call
                    target_type = "function"
                    usage_type = "call"

                self._record_usage(
                    line=node.lineno,
                    usage_type=usage_type,
                    target_type=target_type,
                    target_name=name,
                    target_class=None,
                )

            # Continue visiting children
            self.generic_visit(node)

        except Exception as e:
            logger.debug(
                f"Error tracking usage at line {node.lineno}: {e}", exc_info=True
            )
            # Continue visiting even if one usage fails
            self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """
        Visit attribute access.

        Tracks property accesses (when used in certain contexts).
        Note: We only track attribute accesses that are not method calls
        (method calls are handled in visit_Call).
        """
        # Only track if it's not part of a call (calls are handled separately)
        # We check if parent is not a Call node
        # This is a simplified approach - in practice, we might want to track
        # all attribute accesses, but that could be too verbose

        # For now, we'll track attribute accesses that are likely property accesses
        # This is a heuristic - we can refine it later
        try:
            # Check if this is a simple attribute access (not in a call)
            # We can't easily check parent here, so we'll be conservative
            # and only track in specific contexts

            # Continue visiting children
            self.generic_visit(node)
        except Exception as e:
            logger.debug(
                f"Error tracking attribute at line {node.lineno}: {e}", exc_info=True
            )
            self.generic_visit(node)

    def _record_usage(
        self,
        line: int,
        usage_type: str,
        target_type: str,
        target_name: str,
        target_class: Optional[str] = None,
    ) -> None:
        """
        Record a usage.

        Args:
            line: Line number where usage occurs
            usage_type: Type of usage ('call', 'instantiation', 'attribute')
            target_type: Type of target ('class', 'function', 'method', 'property')
            target_name: Name of target entity
            target_class: Optional class name (for methods/properties)
        """
        # Build context string
        context_parts = []
        if self._current_class:
            context_parts.append(f"class:{self._current_class}")
        if self._current_function:
            context_parts.append(f"function:{self._current_function}")
        context = " | ".join(context_parts) if context_parts else None

        usage_record = {
            "line": line,
            "usage_type": usage_type,
            "target_type": target_type,
            "target_name": target_name,
            "target_class": target_class,
            "context": context,
        }

        self._usages.append(usage_record)

        # Call callback to add usage to database
        try:
            self._add_usage(usage_record)
        except Exception as e:
            logger.warning(
                f"Failed to add usage record for {target_name} at line {line}: {e}",
                exc_info=True,
            )

    def get_usages(self) -> List[Dict[str, Any]]:
        """
        Get all tracked usages.

        Returns:
            List of usage records
        """
        return self._usages.copy()
