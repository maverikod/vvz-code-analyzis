"""
AST normalizer for duplicate detection: variable names, literals, structure.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Dict


class ASTNormalizer(ast.NodeTransformer):
    """
    AST node transformer that normalizes code structure.

    Normalizes:
    - Variable names -> _VAR_, _VAR2_, etc.
    - String literals -> _STR_
    - Numeric literals -> _NUM_
    - Preserves structure (if/for/while/call)
    """

    def __init__(self) -> None:
        """Initialize normalizer."""
        self._var_counter = 0
        self._var_map: Dict[str, str] = {}
        self._str_counter = 0
        self._num_counter = 0

    def _get_var_name(self, name: str) -> str:
        """Get normalized variable name."""
        if name not in self._var_map:
            self._var_counter += 1
            self._var_map[name] = f"_VAR{self._var_counter}_"
        return self._var_map[name]

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """Normalize variable names."""
        if node.id in ("True", "False", "None", "self", "cls"):
            return node
        normalized_id = self._get_var_name(node.id)
        return ast.Name(id=normalized_id, ctx=node.ctx)

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        """Normalize attribute access (keep structure, normalize value if needed)."""
        value = self.visit(node.value)
        return ast.Attribute(value=value, attr=node.attr, ctx=node.ctx)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Normalize function definition (normalize name and arguments)."""
        normalized_name = self._get_var_name(node.name)
        args = self.visit(node.args)
        body = [self.visit(stmt) for stmt in node.body]
        decorator_list = [self.visit(dec) for dec in node.decorator_list]
        return ast.FunctionDef(
            name=normalized_name,
            args=args,
            body=body,
            decorator_list=decorator_list,
            returns=self.visit(node.returns) if node.returns else None,
        )

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """Normalize async function definition."""
        normalized_name = self._get_var_name(node.name)
        args = self.visit(node.args)
        body = [self.visit(stmt) for stmt in node.body]
        decorator_list = [self.visit(dec) for dec in node.decorator_list]
        return ast.AsyncFunctionDef(
            name=normalized_name,
            args=args,
            body=body,
            decorator_list=decorator_list,
            returns=self.visit(node.returns) if node.returns else None,
        )

    def visit_arguments(self, node: ast.arguments) -> ast.arguments:
        """Normalize function arguments."""
        posonlyargs = [self._normalize_arg(arg) for arg in node.posonlyargs]
        args = [self._normalize_arg(arg) for arg in node.args]
        kwonlyargs = [self._normalize_arg(arg) for arg in node.kwonlyargs]
        defaults = [self.visit(default) for default in node.defaults]
        kw_defaults = [
            self.visit(default) if default else None for default in node.kw_defaults
        ]
        return ast.arguments(
            posonlyargs=posonlyargs,
            args=args,
            vararg=self._normalize_arg(node.vararg) if node.vararg else None,
            kwonlyargs=kwonlyargs,
            kwarg=self._normalize_arg(node.kwarg) if node.kwarg else None,
            defaults=defaults,
            kw_defaults=kw_defaults,
        )

    def _normalize_arg(self, arg: ast.arg) -> ast.arg:
        """Normalize function argument."""
        normalized_id = self._get_var_name(arg.arg)
        return ast.arg(
            arg=normalized_id,
            annotation=self.visit(arg.annotation) if arg.annotation else None,
        )

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        """Normalize constants (strings and numbers)."""
        if isinstance(node.value, str):
            self._str_counter += 1
            return ast.Constant(value="_STR_", kind=node.kind)
        elif isinstance(node.value, (int, float, complex)):
            self._num_counter += 1
            return ast.Constant(value="_NUM_", kind=node.kind)
        elif isinstance(node.value, bool):
            return node
        elif node.value is None:
            return node
        else:
            self._str_counter += 1
            return ast.Constant(value="_STR_", kind=node.kind)

    def visit_Str(self, node: ast.Str) -> ast.Constant:
        """Normalize string literals (Python < 3.8 compatibility)."""
        self._str_counter += 1
        return ast.Constant(value="_STR_")

    def visit_Num(self, node: ast.Num) -> ast.Constant:
        """Normalize numeric literals (Python < 3.8 compatibility)."""
        self._num_counter += 1
        return ast.Constant(value="_NUM_")

    def visit_List(self, node: ast.List) -> ast.List:
        """Normalize list literals."""
        elts = [self.visit(elt) for elt in node.elts]
        return ast.List(elts=elts, ctx=node.ctx)

    def visit_Dict(self, node: ast.Dict) -> ast.Dict:
        """Normalize dict literals."""
        keys = [self.visit(key) if key else None for key in node.keys]
        values = [self.visit(value) for value in node.values]
        return ast.Dict(keys=keys, values=values)

    def visit_Tuple(self, node: ast.Tuple) -> ast.Tuple:
        """Normalize tuple literals."""
        elts = [self.visit(elt) for elt in node.elts]
        return ast.Tuple(elts=elts, ctx=node.ctx)
