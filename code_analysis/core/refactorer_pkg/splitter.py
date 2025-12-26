"""
Module splitter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

from .base import BaseRefactorer
try:
    from .formatters import format_code_with_black, format_error_message
except ImportError:
    from .utils import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


class ClassSplitter(BaseRefactorer):
    """Class for splitting classes into smaller components."""

    def _build_new_class_code(
        self,
        dst_class_name: str,
        src_class: ast.ClassDef,
        dst_config: Dict[str, Any],
        base_indent: int = 0,
    ) -> str:
        """
        Build destination class as source code string.

        This path is used to preserve original formatting and comments by slicing
        method bodies from the original source.
        """
        class_indent = " " * base_indent
        indent = class_indent + "    "
        lines: list[str] = [f"{class_indent}class {dst_class_name}:"]

        docstring = ast.get_docstring(src_class)
        if docstring:
            lines.append(f'{indent}"""{docstring}"""')

        props = dst_config.get("props", []) or []
        if props:
            lines.append(f"{indent}def __init__(self):")
            init_indent = indent + "    "
            for prop in props:
                lines.append(f"{init_indent}self.{prop} = None")

        methods = dst_config.get("methods", []) or []
        for method_name in methods:
            method_node = self._find_method_in_class(src_class, method_name)
            if not method_node:
                logger.warning(
                    f"Method {method_name} not found in source class for destination class {dst_class_name}"
                )
                continue
            method_code = self._extract_method_code(method_node, indent)
            if method_code.strip():
                lines.append(method_code)

        if len(lines) == 1:
            lines.append(f"{indent}pass")
        return "\n".join(lines)

    def _build_new_class(
        self,
        dst_class_name: str,
        src_class: ast.ClassDef,
        dst_config: Dict[str, Any],
        base_indent: int = 0,
    ) -> str:
        """
        Compatibility wrapper for older tests.

        Historically, splitter returned generated class code as a string.
        The current implementation builds an AST node. This method keeps the
        old behavior for test coverage and backward compatibility.
        """
        _ = base_indent
        node = self._build_new_class_ast(dst_class_name, src_class, dst_config)
        node = ast.fix_missing_locations(node)
        return ast.unparse(node)

    def extract_class_members(self, class_node: ast.ClassDef) -> Dict[str, List[Any]]:
        """Extract all properties and methods from class."""
        members: Dict[str, List[Any]] = {
            "properties": [],
            "methods": [],
            "nested_classes": [],
        }
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members["methods"].append(item)
            elif isinstance(item, ast.ClassDef):
                members["nested_classes"].append(item)
        return members

    def validate_split_config(
        self, src_class: ast.ClassDef, config: Dict[str, Any]
    ) -> tuple[bool, List[str]]:
        """Validate split configuration."""
        from .validators import validate_split_config as validate_config_func

        return validate_config_func(src_class, config, self.extract_init_properties)

    def preview_split(
        self, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Preview split without making changes.

        Args:
            config: Split configuration

        Returns:
            Tuple of (success, error_message, preview_content)
        """
        try:
            self.load_file()
            src_class_name = config.get("src_class")
            if not src_class_name:
                return (False, "Source class name not specified in config", None)
            src_class = self.find_class(src_class_name)
            if not src_class:
                return (False, f"Class '{src_class_name}' not found in file", None)
            is_valid, errors = self.validate_split_config(src_class, config)
            if not is_valid:
                error_msg = format_error_message(
                    "config_validation", "; ".join(errors), self.file_path
                )
                return (False, error_msg, None)
            new_content = self._perform_split(src_class, config)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(new_content)
            try:
                format_success, _ = format_code_with_black(tmp_path)
                if format_success:
                    formatted_content = tmp_path.read_text()
                else:
                    formatted_content = new_content
            finally:
                tmp_path.unlink()
            return (True, None, formatted_content)
        except Exception as e:
            error_msg = f"Error during preview: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return (False, error_msg, None)

    def split_class(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Split class according to configuration."""
        try:
            self.create_backup()
            self.load_file()
            src_class_name = config.get("src_class")
            if not src_class_name:
                return (False, "Source class name not specified in config")
            src_class = self.find_class(src_class_name)
            if not src_class:
                return (False, f"Class '{src_class_name}' not found in file")
            original_props = set(self.extract_init_properties(src_class))
            original_methods = set()
            for item in src_class.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    original_methods.add(item.name)
            is_valid, errors = self.validate_split_config(src_class, config)
            if not is_valid:
                error_msg = format_error_message(
                    "config_validation", "; ".join(errors), self.file_path
                )
                return (False, error_msg)
            new_content = self._perform_split(src_class, config)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            format_success, format_error = format_code_with_black(self.file_path)
            if not format_success:
                logger.warning(f"Code formatting failed (continuing): {format_error}")
            is_valid, error_msg = self.validate_python_syntax()
            if not is_valid:
                self.restore_backup()
                return (False, f"Python validation failed: {error_msg}")
            is_complete, completeness_error = self.validate_completeness(
                src_class_name, config, original_props, original_methods
            )
            if not is_complete:
                self.restore_backup()
                formatted_error = format_error_message(
                    "completeness", completeness_error, self.file_path
                )
                return (False, formatted_error)
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                src_class, config
            )
            if not is_docstrings_valid:
                self.restore_backup()
                formatted_error = format_error_message(
                    "docstring", docstrings_error, self.file_path
                )
                return (False, formatted_error)
            try:
                import_valid, import_error = self.validate_imports()
                if not import_valid:
                    logger.warning(f"Import validation warning: {import_error}")
            except Exception as e:
                logger.warning(f"Import validation skipped: {e}")
            return (True, "Split completed successfully")
        except Exception as e:
            if self.backup_path:
                self.restore_backup()
            return (False, f"Error during split: {str(e)}")

    def _perform_split(self, src_class: ast.ClassDef, config: Dict[str, Any]) -> str:
        """
        Perform the actual class splitting using source slicing.

        We intentionally avoid `ast.unparse` here because it drops comments.
        """
        if not self.tree:
            raise ValueError("AST tree not loaded")
        dst_classes = config.get("dst_classes", {})
        method_mapping: Dict[str, str] = {}
        prop_mapping: Dict[str, str] = {}
        for dst_class_name, dst_config in dst_classes.items():
            for method in dst_config.get("methods", []):
                method_mapping[method] = dst_class_name
            for prop in dst_config.get("props", []):
                prop_mapping[prop] = dst_class_name
        if not hasattr(src_class, "lineno"):
            raise ValueError("Source class has no source location information")
        lines = self.original_content.split("\n")
        start = src_class.lineno - 1
        end = (
            src_class.end_lineno
            if hasattr(src_class, "end_lineno") and src_class.end_lineno
            else self._find_class_end(src_class, lines)
        )
        before = "\n".join(lines[:start]).rstrip("\n")
        after = "\n".join(lines[end:]).lstrip("\n")

        modified_src = self._build_modified_source_class(
            src_class, method_mapping, prop_mapping, dst_classes, base_indent=0
        )
        new_classes: list[str] = []
        for dst_class_name, dst_config in dst_classes.items():
            new_classes.append(
                self._build_new_class_code(
                    dst_class_name, src_class, dst_config, base_indent=0
                )
            )

        parts: list[str] = []
        if before.strip():
            parts.append(before)
        parts.append(modified_src)
        parts.extend(new_classes)
        if after.strip():
            parts.append(after)

        return "\n\n".join(parts).rstrip() + "\n"

    def _get_indent(self, line: str) -> int:
        """Get indentation level of a line."""
        return len(line) - len(line.lstrip())

    def _build_new_class_ast(
        self, dst_class_name: str, src_class: ast.ClassDef, dst_config: Dict[str, Any]
    ) -> ast.ClassDef:
        """Build AST node for a new destination class."""
        methods = dst_config.get("methods", [])
        props = dst_config.get("props", [])
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
            method_node = self._find_method_in_class(src_class, method_name)
            if method_node:
                import copy

                new_method = copy.deepcopy(method_node)
                class_body.append(new_method)
            else:
                logger.warning(
                    f"Method {method_name} not found in source class for destination class {dst_class_name}"
                )
        new_class = ast.ClassDef(
            name=dst_class_name,
            bases=[],
            keywords=[],
            body=class_body if class_body else [ast.Pass()],
            decorator_list=[],
        )
        return new_class

    def _build_modified_source_class_ast(
        self,
        src_class: ast.ClassDef,
        method_mapping: Dict[str, str],
        prop_mapping: Dict[str, str],
        dst_classes: Dict[str, Dict[str, Any]],
    ) -> ast.ClassDef:
        """Build modified source class AST node with wrappers and property references."""
        import copy

        modified_class = copy.deepcopy(src_class)
        all_methods = set()
        for item in modified_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_methods.add(item.name)
        moved_methods = set(method_mapping.keys())
        all_methods - moved_methods
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
                func=ast.Name(id=dst_class_name, ctx=ast.Load()), args=[], keywords=[]
            )
            assign = ast.Assign(targets=[target], value=value)
            init_body.append(assign)
        all_props = set(self.extract_init_properties(src_class))
        moved_props = set(prop_mapping.keys())
        remaining_props = all_props - moved_props
        original_init = self._find_method_in_class(src_class, "__init__")
        if original_init:
            for stmt in original_init.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Attribute):
                            if (
                                isinstance(target.value, ast.Name)
                                and target.value.id == "self"
                                and (target.attr in remaining_props)
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
            original_method = self._find_method_in_class(src_class, method_name)
            if original_method:
                dst_var = (
                    dst_class_name[0].lower() + dst_class_name[1:]
                    if dst_class_name
                    else dst_class_name.lower()
                )
                call_args = []
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
                        [ast.Return(value=call)]
                        if call_args
                        else [ast.Expr(value=call)]
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

    def _build_modified_source_class(
        self,
        src_class: ast.ClassDef,
        method_mapping: Dict[str, str],
        prop_mapping: Dict[str, str],
        dst_classes: Dict[str, Dict[str, Any]],
        base_indent: int,
    ) -> str:
        """Build modified source class with wrappers and property references."""
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
        for dst_class_name, props in prop_groups.items():
            instance_name = (
                dst_class_name[0].lower() + dst_class_name[1:]
                if dst_class_name
                else dst_class_name.lower()
            )
            lines.append(f"{init_indent}self.{instance_name} = {dst_class_name}()")
            init_has_body = True
        all_props = set(self.extract_init_properties(src_class))
        moved_props = set(prop_mapping.keys())
        remaining_props = all_props - moved_props
        init_method = self._find_method_in_class(src_class, "__init__")
        if init_method:
            init_lines = self.original_content.split("\n")
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
                        original_indent = len(line) - len(line.lstrip())
                        new_indent = init_indent + " " * (
                            original_indent - (init_method.lineno - 1)
                        )
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
            method_node = self._find_method_in_class(src_class, method_name)
            if method_node:
                method_code = self._extract_method_code(method_node, indent)
                lines.append(method_code)
        for method_name, dst_class_name in method_mapping.items():
            wrapper = self._create_method_wrapper(method_name, dst_class_name, indent)
            lines.append(wrapper)
        return "\n".join(lines)

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

    def validate_completeness(
        self,
        src_class_name: str,
        config: Dict[str, Any],
        original_props: set,
        original_methods: set,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all original properties and methods are present.

        Uses pre-collected original_props and original_methods for strict
        validation against the refactored code.
        """
        from .validators import (
            validate_completeness_split as validate_completeness_func,
        )

        return validate_completeness_func(
            self.file_path,
            src_class_name,
            config,
            original_props,
            original_methods,
            self.extract_init_properties,
        )

    def validate_docstrings(
        self, src_class: ast.ClassDef, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all docstrings are preserved in destination classes.

        Args:
            src_class: Original source class AST node
            config: Split configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))
            src_class_docstring = ast.get_docstring(src_class)
            src_method_docstrings = {}
            for item in src_class.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_docstring = ast.get_docstring(item)
                    if method_docstring:
                        src_method_docstrings[item.name] = method_docstring
            dst_classes = {}
            dst_classes_config = config.get("dst_classes", {})
            for dst_class_name in dst_classes_config.keys():
                for node in ast.walk(new_tree):
                    if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                        dst_classes[dst_class_name] = node
                        break
            if src_class_docstring:
                found_in_dst = False
                for dst_class_name, dst_class_node in dst_classes.items():
                    dst_docstring = ast.get_docstring(dst_class_node)
                    if (
                        dst_docstring
                        and dst_docstring.strip() == src_class_docstring.strip()
                    ):
                        found_in_dst = True
                        break
                if not found_in_dst:
                    return (
                        False,
                        f"Class docstring not found in destination classes. Expected: {src_class_docstring[:50]}...",
                    )
            method_mapping: Dict[str, str] = {}
            for dst_class_name, dst_config in dst_classes_config.items():
                for method in dst_config.get("methods", []):
                    method_mapping[method] = dst_class_name
            for method_name, method_docstring in src_method_docstrings.items():
                if method_name in method_mapping:
                    dst_class_name = method_mapping[method_name]
                    dst_class_node = dst_classes.get(dst_class_name)
                    if not dst_class_node:
                        return (
                            False,
                            f"Destination class '{dst_class_name}' not found for method '{method_name}'",
                        )
                    method_found = False
                    for item in dst_class_node.body:
                        if (
                            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and item.name == method_name
                        ):
                            dst_method_docstring = ast.get_docstring(item)
                            if not dst_method_docstring:
                                return (
                                    False,
                                    f"Method '{method_name}' docstring missing in destination class '{dst_class_name}'. Expected: {method_docstring[:50]}...",
                                )
                            if dst_method_docstring.strip() != method_docstring.strip():
                                return (
                                    False,
                                    f"Method '{method_name}' docstring mismatch in destination class '{dst_class_name}'. Expected: {method_docstring[:50]}..., Got: {dst_method_docstring[:50]}...",
                                )
                            method_found = True
                            break
                    if not method_found:
                        return (
                            False,
                            f"Method '{method_name}' not found in destination class '{dst_class_name}'",
                        )
            return (True, None)
        except Exception as e:
            return (False, f"Error during docstring validation: {str(e)}")
