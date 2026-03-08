"""
AST building for class splitter: new class AST and modified source class AST.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import copy
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


def build_new_class_ast(
    dst_class_name: str,
    src_class: ast.ClassDef,
    dst_config: Dict[str, Any],
    find_method_in_class: Callable[[ast.ClassDef, str], Any],
) -> ast.ClassDef:
    """Build AST node for a new destination class."""
    methods = dst_config.get("methods", []) or []
    props = dst_config.get("props", []) or []
    class_body: List[ast.stmt] = []
    if src_class.body and isinstance(src_class.body[0], ast.Expr):
        docstring = ast.get_docstring(src_class)
        if docstring:
            class_body.append(ast.Expr(ast.Constant(value=docstring)))
    if props:
        init_body: List[ast.stmt] = []
        for prop in props:
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
            body=init_body if init_body else [ast.Pass()],
            decorator_list=[],
            returns=None,
        )
        class_body.append(init_method)
    for method_name in methods:
        method_node = find_method_in_class(src_class, method_name)
        if method_node:
            new_method = copy.deepcopy(method_node)
            class_body.append(new_method)
        else:
            logger.warning(
                "Method %s not found in source class for destination class %s",
                method_name,
                dst_class_name,
            )
    new_class = ast.ClassDef(
        name=dst_class_name,
        bases=[],
        keywords=[],
        body=class_body if class_body else [ast.Pass()],
        decorator_list=[],
    )
    return new_class


def build_modified_source_class_ast(
    src_class: ast.ClassDef,
    method_mapping: Dict[str, str],
    prop_mapping: Dict[str, str],
    dst_classes: Dict[str, Dict[str, Any]],
    extract_init_properties: Callable[[ast.ClassDef], List[str]],
    find_method_in_class: Callable[[ast.ClassDef, str], Any],
) -> ast.ClassDef:
    """Build modified source class AST with wrappers and property references."""
    modified_class = copy.deepcopy(src_class)
    all_methods = set()
    for item in modified_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_methods.add(item.name)
    moved_methods = set(method_mapping.keys())
    _ = all_methods - moved_methods  # for clarity of intent
    new_body: List[ast.stmt] = []
    if modified_class.body and isinstance(modified_class.body[0], ast.Expr):
        docstring = ast.get_docstring(modified_class)
        if docstring:
            new_body.append(ast.Expr(ast.Constant(value=docstring)))
    init_body: List[ast.stmt] = []
    prop_groups: Dict[str, List[str]] = {}
    for prop, dst_class in prop_mapping.items():
        if dst_class not in prop_groups:
            prop_groups[dst_class] = []
        prop_groups[dst_class].append(prop)
    for dst_class_name, props in prop_groups.items():
        instance_name = (
            dst_class_name[0].lower() + dst_class_name[1:]
            if dst_class_name
            else dst_class_name.lower()
        )
        target = ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()),
            attr=instance_name,
            ctx=ast.Store(),
        )
        value = ast.Call(
            func=ast.Name(id=dst_class_name, ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        assign = ast.Assign(targets=[target], value=value)
        init_body.append(assign)
    all_props = set(extract_init_properties(src_class))
    moved_props = set(prop_mapping.keys())
    remaining_props = all_props - moved_props
    original_init = find_method_in_class(src_class, "__init__")
    if original_init:
        for stmt in original_init.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Attribute):
                        if (
                            isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "self"
                            and (tgt.attr in remaining_props)
                        ):
                            init_body.append(copy.deepcopy(stmt))
                            break
            elif isinstance(stmt, ast.AnnAssign):
                if (
                    isinstance(stmt.target, ast.Attribute)
                    and isinstance(stmt.target.value, ast.Name)
                    and (stmt.target.value.id == "self")
                    and (stmt.target.attr in remaining_props)
                ):
                    init_body.append(copy.deepcopy(stmt))
    if init_body:
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
        new_body.append(init_method)
    for method_name, dst_class_name in method_mapping.items():
        original_method = find_method_in_class(src_class, method_name)
        if original_method:
            dst_var = (
                dst_class_name[0].lower() + dst_class_name[1:]
                if dst_class_name
                else dst_class_name.lower()
            )
            call_args: List[ast.expr] = []
            if isinstance(original_method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in original_method.args.args[1:]:
                    call_args.append(ast.Name(id=arg.arg, ctx=ast.Load()))
            call = ast.Call(
                func=ast.Attribute(
                    value=ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=dst_var,
                        ctx=ast.Load(),
                    ),
                    attr=method_name,
                    ctx=ast.Load(),
                ),
                args=call_args,
                keywords=[],
            )
            wrapper_method = ast.FunctionDef(
                name=method_name,
                args=original_method.args,
                body=(
                    [ast.Return(value=call)] if call_args else [ast.Expr(value=call)]
                ),
                decorator_list=copy.deepcopy(original_method.decorator_list),
                returns=copy.deepcopy(original_method.returns),
            )
            new_body.append(wrapper_method)
    for item in modified_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name not in moved_methods and item.name != "__init__":
                new_body.append(item)
    modified_class.body = new_body if new_body else [ast.Pass()]
    return modified_class
