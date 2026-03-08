"""
Source-code building for class splitter: modified source class and method wrappers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Any, Callable, Dict, List, Optional


def build_modified_source_class(
    src_class: ast.ClassDef,
    method_mapping: Dict[str, str],
    prop_mapping: Dict[str, str],
    dst_classes: Dict[str, Dict[str, Any]],
    base_indent: int,
    original_content: str,
    extract_init_properties: Callable[[ast.ClassDef], List[str]],
    find_method_in_class: Callable[[ast.ClassDef, str], Any],
    extract_method_code: Callable[[Any, str], str],
    create_method_wrapper: Callable[[str, str, str], str],
) -> str:
    """Build modified source class as string with wrappers and property refs."""
    indent = " " * base_indent
    lines = [f"{indent}class {src_class.name}:"]
    indent += "    "
    docstring = ast.get_docstring(src_class)
    if docstring:
        lines.append(f'{indent}"""{docstring}"""')
    lines.append(f"{indent}def __init__(self):")
    init_indent = indent + "    "
    init_has_body = False
    prop_groups: Dict[str, List[str]] = {}
    for prop, dst_class in prop_mapping.items():
        if dst_class not in prop_groups:
            prop_groups[dst_class] = []
        prop_groups[dst_class].append(prop)
    for dst_class_name, _ in prop_groups.items():
        instance_name = (
            dst_class_name[0].lower() + dst_class_name[1:]
            if dst_class_name
            else dst_class_name.lower()
        )
        lines.append(f"{init_indent}self.{instance_name} = {dst_class_name}()")
        init_has_body = True
    all_props = set(extract_init_properties(src_class))
    moved_props = set(prop_mapping.keys())
    remaining_props = all_props - moved_props
    init_method = find_method_in_class(src_class, "__init__")
    if init_method:
        init_lines = original_content.split("\n")
        init_start = init_method.lineno - 1
        init_end = (
            init_method.end_lineno
            if hasattr(init_method, "end_lineno") and init_method.end_lineno
            else init_start + 10
        )
        for i in range(init_start, min(init_end, len(init_lines))):
            line = init_lines[i]
            for prop in remaining_props:
                if f"self.{prop}" in line and "=" in line:
                    base_off = init_method.lineno - 1
                    original_indent = len(line) - len(line.lstrip())
                    new_indent = init_indent + " " * (original_indent - base_off)
                    lines.append(new_indent + line.lstrip())
                    init_has_body = True
                    break
    if not init_has_body:
        lines.append(f"{init_indent}pass")
    all_methods = set()
    for item in src_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_methods.add(item.name)
    moved_methods = set(method_mapping.keys())
    remaining_methods = all_methods - moved_methods - {"__init__"}
    for method_name in remaining_methods:
        method_node = find_method_in_class(src_class, method_name)
        if method_node:
            method_code = extract_method_code(method_node, indent)
            lines.append(method_code)
    for method_name, dst_class_name in method_mapping.items():
        wrapper = create_method_wrapper(method_name, dst_class_name, indent)
        lines.append(wrapper)
    return "\n".join(lines)


def create_method_wrapper_impl(
    tree: Optional[ast.Module],
    method_name: str,
    dst_class_name: str,
    indent: str,
) -> str:
    """Create a wrapper method string that delegates to the destination class."""
    method_node: Optional[Any] = None
    if tree:
        for node in ast.walk(tree):
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
