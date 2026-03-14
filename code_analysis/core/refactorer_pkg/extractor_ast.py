"""
AST helpers for superclass extraction: build base class, update child class.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import copy
from typing import Any, Callable, Dict, List, Optional


def is_self_assignment_to_any(stmt: ast.stmt, props: set[str]) -> bool:
    """Detect `self.<prop> = ...` or annotated assignment to `self.<prop>`."""
    if isinstance(stmt, ast.Assign):
        for t in stmt.targets:
            if (
                isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"
                and t.attr in props
            ):
                return True
    if isinstance(stmt, ast.AnnAssign):
        t = stmt.target
        if (
            isinstance(t, ast.Attribute)
            and isinstance(t.value, ast.Name)
            and t.value.id == "self"
            and t.attr in props
        ):
            return True
    return False


def build_base_class_ast(
    base_class_name: str,
    child_nodes: List[ast.ClassDef],
    extract_from: Dict[str, Dict[str, Any]],
    abstract_methods: List[str],
    find_method_in_class: Callable[[ast.ClassDef, str], Optional[ast.FunctionDef]],
) -> ast.ClassDef:
    """Build the base class as AST node."""
    needs_abc = bool(abstract_methods)
    class_body: List[ast.stmt] = []
    docstring_node = ast.Expr(
        ast.Constant(value="Base class with common functionality.")
    )
    class_body.append(docstring_node)
    all_props = set()
    for child_config in extract_from.values():
        all_props.update(child_config.get("properties", []))
        all_props.update(child_config.get("props", []))
    if all_props:
        init_body: List[ast.stmt] = []
        for prop in sorted(all_props):
            target = ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=prop,
                ctx=ast.Store(),
            )
            assign = ast.Assign(targets=[target], value=ast.Constant(value=None))
            init_body.append(assign)
        init_method = ast.FunctionDef(
            name="__init__",
            args=ast.arguments(
                args=[ast.arg(arg="self")],
                posonlyargs=[],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=init_body,
            decorator_list=[],
            returns=None,
        )
        class_body.append(init_method)
    all_methods = set()
    for child_config in extract_from.values():
        all_methods.update(child_config.get("methods", []))
    first_child = child_nodes[0]
    for method_name in sorted(all_methods):
        method_node = find_method_in_class(first_child, method_name)
        if method_node:
            if method_name in abstract_methods:
                abstract_method = copy.deepcopy(method_node)
                abstract_method.decorator_list.insert(
                    0, ast.Name(id="abstractmethod", ctx=ast.Load())
                )
                abstract_method.body = [
                    ast.Raise(
                        exc=ast.Call(
                            func=ast.Name(id="NotImplementedError", ctx=ast.Load()),
                            args=[],
                            keywords=[],
                        ),
                        cause=None,
                    )
                ]
                class_body.append(abstract_method)
            else:
                new_method = copy.deepcopy(method_node)
                class_body.append(new_method)
    bases: list[ast.expr] = []
    if needs_abc:
        bases.append(ast.Name(id="ABC", ctx=ast.Load()))
    base_class = ast.ClassDef(
        name=base_class_name,
        bases=bases,
        keywords=[],
        body=class_body if class_body else [ast.Pass()],
        decorator_list=[],
    )
    return base_class


def update_child_class_ast(
    child_node: ast.ClassDef,
    base_class_name: str,
    child_config: Dict[str, Any],
    is_self_assign: Callable[[ast.stmt, set], bool],
) -> ast.ClassDef:
    """Update child class AST: inherit from base, remove extracted members."""
    updated_class = copy.deepcopy(child_node)
    extracted_methods = set(child_config.get("methods", []))
    extracted_props = set(child_config.get("properties", []))
    extracted_props.update(child_config.get("props", []))
    base_name_node = ast.Name(id=base_class_name, ctx=ast.Load())
    if updated_class.bases:
        updated_class.bases.insert(0, base_name_node)
    else:
        updated_class.bases = [base_name_node]
    new_body: List[ast.stmt] = []
    if updated_class.body and isinstance(updated_class.body[0], ast.Expr):
        docstring = ast.get_docstring(updated_class)
        if docstring:
            new_body.append(ast.Expr(ast.Constant(value=docstring)))
    for item in updated_class.body:
        if isinstance(item, ast.Expr):
            continue
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name in extracted_methods:
                continue
            if item.name == "__init__" and extracted_props:
                new_init_body: List[ast.stmt] = []
                for stmt in item.body:
                    if is_self_assign(stmt, extracted_props):
                        continue
                    new_init_body.append(stmt)
                if not new_init_body:
                    new_init_body = [ast.Pass()]
                item.body = new_init_body
            new_body.append(item)
        else:
            new_body.append(item)
    if not new_body or (len(new_body) == 1 and isinstance(new_body[0], ast.Expr)):
        new_body.append(ast.Pass())
    updated_class.body = new_body
    return updated_class
