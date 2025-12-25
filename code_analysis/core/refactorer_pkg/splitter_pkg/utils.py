"""
Module utils.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


def _get_indent(self, line: str) -> int:
    """Get indentation level of a line."""
    return len(line) - len(line.lstrip())


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


def _create_method_wrapper(
    self, method_name: str, dst_class_name: str, indent: str
) -> str:
    """Create a wrapper method that delegates to the destination class."""
    method_node = None
    if self.tree:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        method_node = item
                        break
                if method_node:
                    break
    if method_node:
        args = [arg.arg for arg in method_node.args.args]
        if args and args[0] == "self":
            args = args[1:]
        args_str = ", ".join(["self"] + args)
        dst_var = (
            dst_class_name[0].lower() + dst_class_name[1:]
            if dst_class_name
            else dst_class_name.lower()
        )
        call_args = ", ".join(args) if args else ""
        wrapper_lines = [
            f"{indent}def {method_name}({args_str}):",
            f"{indent}    return self.{dst_var}.{method_name}({call_args})",
        ]
        if isinstance(method_node, ast.AsyncFunctionDef):
            wrapper_lines[0] = f"{indent}async def {method_name}({args_str}):"
        return "\n".join(wrapper_lines)
    return ""
