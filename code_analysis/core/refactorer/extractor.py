"""
Module extractor.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

from .base import BaseRefactorer
from .formatters import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


class SuperclassExtractor(BaseRefactorer):
    """Class for extracting common functionality into base class."""

    def _build_base_class(
        self,
        base_class_name: str,
        child_nodes: List[Optional[ast.ClassDef]],
        extract_from: Dict[str, Dict[str, Any]],
        abstract_methods: List[str],
    ) -> str:
        """
        Compatibility wrapper for older tests.

        Returns the base class source code as a string.
        """
        real_children = [c for c in child_nodes if c is not None]
        node = self._build_base_class_ast(
            base_class_name=base_class_name,
            child_nodes=real_children,
            extract_from=extract_from,
            abstract_methods=abstract_methods,
        )
        node = ast.fix_missing_locations(node)
        return ast.unparse(node)

    def _update_child_class(
        self,
        child_node: ast.ClassDef,
        base_class_name: str,
        child_config: Dict[str, Any],
        lines: List[str],
    ) -> str:
        """
        Compatibility wrapper for older tests.

        Returns updated child class code as a string.
        """
        _ = lines
        node = self._update_child_class_ast(child_node, base_class_name, child_config)
        node = ast.fix_missing_locations(node)
        return ast.unparse(node)

    def get_class_bases(self, class_node: ast.ClassDef) -> List[str]:
        """Get list of base class names."""
        bases = []
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                parts = []
                node = base
                while isinstance(node, ast.Attribute):
                    parts.append(node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    parts.append(node.id)
                    bases.append(".".join(reversed(parts)))
        return bases

    def check_multiple_inheritance_conflicts(
        self, child_classes: List[str], base_class: Optional[str]
    ) -> tuple[bool, Optional[str]]:
        """Check for multiple inheritance conflicts."""
        if not self.tree:
            return (False, "AST tree not loaded")
        all_bases: Dict[str, List[str]] = {}
        for child_name in child_classes:
            child_node = self.find_class(child_name)
            if child_node:
                bases = self.get_class_bases(child_node)
                all_bases[child_name] = bases
        conflicts = []
        for child_name, bases in all_bases.items():
            if bases:
                conflicts.append(f"{child_name} already inherits from {bases}")
        if conflicts:
            return (False, f"Multiple inheritance conflicts: {'; '.join(conflicts)}")
        return (True, None)

    def check_method_compatibility(
        self, class_names: List[str], method_name: str
    ) -> tuple[bool, Optional[str]]:
        """Check if method has compatible signature across classes."""
        methods = []
        for class_name in class_names:
            class_node = self.find_class(class_name)
            if class_node:
                method = self._find_method_in_class(class_node, method_name)
                if method:
                    methods.append(method)
        if not methods:
            return (True, None)
        if len(methods) != len(class_names):
            return (False, f"Method {method_name} not found in all classes")
        first_method = methods[0]
        first_args = [arg.arg for arg in first_method.args.args]
        first_returns = self._get_return_type(first_method)
        for i, method in enumerate(methods[1:], 1):
            args = [arg.arg for arg in method.args.args]
            returns = self._get_return_type(method)
            if args != first_args:
                return (
                    False,
                    f"Method {method_name} has incompatible signatures in class {class_names[i]}",
                )
            if returns != first_returns:
                return (
                    False,
                    f"Method {method_name} has incompatible return types in class {class_names[i]}",
                )
        return (True, None)

    def _find_method_in_class(
        self, class_node: ast.ClassDef, method_name: str
    ) -> Optional[ast.FunctionDef]:
        """Find a method node in a class."""
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == method_name:
                    return item
        return None

    def _get_return_type(self, method_node: ast.FunctionDef) -> Optional[str]:
        """Extract return type annotation from method."""
        if method_node.returns:
            if isinstance(method_node.returns, ast.Name):
                return method_node.returns.id
        return None

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate extraction configuration."""
        from .validators import validate_extraction_config as validate_config_func

        return validate_config_func(config, self.find_class)

    def validate_completeness(
        self, base_class_name: str, child_classes: List[str], config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate that all members are present after extraction."""
        from .validators import (
            validate_completeness_extraction as validate_completeness_func,
        )

        return validate_completeness_func(
            self.file_path,
            base_class_name,
            child_classes,
            config,
            self.extract_init_properties,
        )

    def validate_docstrings(
        self, child_nodes: List[ast.ClassDef], config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all docstrings are preserved in base and child classes.

        Args:
            child_nodes: Original child class AST nodes
            config: Extraction configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))
            base_class_name = config.get("base_class")
            extract_from = config.get("extract_from", {})
            base_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                    base_class = node
                    break
            if not base_class:
                return (
                    False,
                    f"Base class '{base_class_name}' not found after extraction",
                )
            for child_node in child_nodes:
                child_name = child_node.name
                child_config = extract_from.get(child_name, {})
                new_child_class = None
                for node in ast.walk(new_tree):
                    if isinstance(node, ast.ClassDef) and node.name == child_name:
                        new_child_class = node
                        break
                if not new_child_class:
                    return (
                        False,
                        f"Child class '{child_name}' not found after extraction",
                    )
                original_child_docstring = ast.get_docstring(child_node)
                if original_child_docstring:
                    new_child_docstring = ast.get_docstring(new_child_class)
                    if not new_child_docstring:
                        return (
                            False,
                            f"Child class '{child_name}' docstring missing. Expected: {original_child_docstring[:50]}...",
                        )
                    if new_child_docstring.strip() != original_child_docstring.strip():
                        return (
                            False,
                            f"Child class '{child_name}' docstring mismatch. Expected: {original_child_docstring[:50]}..., Got: {new_child_docstring[:50]}...",
                        )
                extracted_methods = set(child_config.get("methods", []))
                all_extracted_methods = set()
                for cfg in extract_from.values():
                    all_extracted_methods.update(cfg.get("methods", []))
                first_child = child_nodes[0] if child_nodes else None
                for method_name in extracted_methods:
                    original_method = None
                    for item in child_node.body:
                        if (
                            isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and item.name == method_name
                        ):
                            original_method = item
                            break
                    if original_method:
                        original_method_docstring = ast.get_docstring(original_method)
                        if original_method_docstring:
                            base_method = None
                            for item in base_class.body:
                                if (
                                    isinstance(
                                        item, (ast.FunctionDef, ast.AsyncFunctionDef)
                                    )
                                    and item.name == method_name
                                ):
                                    base_method = item
                                    break
                            if not base_method:
                                return (
                                    False,
                                    f"Method '{method_name}' not found in base class '{base_class_name}' after extraction",
                                )
                            base_method_docstring = ast.get_docstring(base_method)
                            if not base_method_docstring:
                                return (
                                    False,
                                    f"Method '{method_name}' docstring missing in base class '{base_class_name}'. Expected: {original_method_docstring[:50]}...",
                                )
                            if (
                                method_name in all_extracted_methods
                                and first_child
                                and first_child is not child_node
                            ):
                                first_child_method = None
                                for item in first_child.body:
                                    if (
                                        isinstance(
                                            item,
                                            (ast.FunctionDef, ast.AsyncFunctionDef),
                                        )
                                        and item.name == method_name
                                    ):
                                        first_child_method = item
                                        break
                                if first_child_method:
                                    first_child_docstring = ast.get_docstring(
                                        first_child_method
                                    )
                                    if first_child_docstring and (
                                        base_method_docstring.strip()
                                        != first_child_docstring.strip()
                                    ):
                                        return (
                                            False,
                                            f"Method '{method_name}' docstring mismatch in base class '{base_class_name}'. Expected (from first class '{first_child.name}'): {first_child_docstring[:50]}..., Got: {base_method_docstring[:50]}...",
                                        )
                            elif (
                                base_method_docstring.strip()
                                != original_method_docstring.strip()
                            ):
                                return (
                                    False,
                                    f"Method '{method_name}' docstring mismatch in base class '{base_class_name}'. Expected: {original_method_docstring[:50]}..., Got: {base_method_docstring[:50]}...",
                                )
            return (True, None)
        except Exception as e:
            return (False, f"Error during docstring validation: {str(e)}")

    def preview_extraction(
        self, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Preview extraction without making changes.

        Args:
            config: Extraction configuration

        Returns:
            Tuple of (success, error_message, preview_content)
        """
        try:
            self.load_file()
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                error_msg = format_error_message(
                    "config_validation", "; ".join(errors), self.file_path
                )
                return (False, error_msg, None)
            base_class_name = config.get("base_class")
            child_classes = config.get("child_classes", [])
            conflict_valid, conflict_error = self.check_multiple_inheritance_conflicts(
                child_classes, base_class_name
            )
            if not conflict_valid:
                return (False, conflict_error, None)
            child_nodes = []
            for child_name in child_classes:
                child_node = self.find_class(child_name)
                if not child_node:
                    return (False, f"Child class '{child_name}' not found", None)
                child_nodes.append(child_node)
            all_methods = set()
            extract_from = config.get("extract_from", {})
            for child_config in extract_from.values():
                all_methods.update(child_config.get("methods", []))
            for method_name in all_methods:
                is_compatible, error = self.check_method_compatibility(
                    child_classes, method_name
                )
                if not is_compatible:
                    return (False, error, None)
            new_content = self._perform_extraction(config, child_nodes)
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

    def extract_superclass(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Extract common functionality into base class."""
        try:
            self.create_backup()
            self.load_file()
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                error_msg = format_error_message(
                    "config_validation", "; ".join(errors), self.file_path
                )
                return (False, error_msg)
            base_class_name = config.get("base_class")
            child_classes = config.get("child_classes", [])
            conflict_valid, conflict_error = self.check_multiple_inheritance_conflicts(
                child_classes, base_class_name
            )
            if not conflict_valid:
                return (False, conflict_error)
            child_nodes = []
            for child_name in child_classes:
                child_node = self.find_class(child_name)
                if not child_node:
                    return (False, f"Child class '{child_name}' not found")
                child_nodes.append(child_node)
            config.get("abstract_methods", [])
            all_methods = set()
            extract_from = config.get("extract_from", {})
            for child_config in extract_from.values():
                all_methods.update(child_config.get("methods", []))
            for method_name in all_methods:
                is_compatible, error = self.check_method_compatibility(
                    child_classes, method_name
                )
                if not is_compatible:
                    return (False, error)
            new_content = self._perform_extraction(config, child_nodes)
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            format_success, format_error = format_code_with_black(self.file_path)
            if not format_success:
                logger.warning(f"Code formatting failed (continuing): {format_error}")
            is_valid, error_msg = self.validate_python_syntax()
            if not is_valid:
                self.restore_backup()
                formatted_error = format_error_message(
                    "python_syntax", error_msg, self.file_path
                )
                return (False, formatted_error)
            is_complete, completeness_error = self.validate_completeness(
                base_class_name, child_classes, config
            )
            if not is_complete:
                self.restore_backup()
                formatted_error = format_error_message(
                    "completeness", completeness_error, self.file_path
                )
                return (False, formatted_error)
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                child_nodes, config
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
            return (True, "Superclass extraction completed successfully")
        except Exception as e:
            if self.backup_path:
                self.restore_backup()
            return (False, f"Error during extraction: {str(e)}")

    def _perform_extraction(
        self, config: Dict[str, Any], child_nodes: List[ast.ClassDef]
    ) -> str:
        """
        Perform the actual superclass extraction using source slicing.

        We intentionally avoid `ast.unparse` for the module rewrite because it drops
        comments from extracted methods.
        """
        if not self.tree:
            raise ValueError("AST tree not loaded")
        base_class_name = config.get("base_class")
        extract_from = config.get("extract_from", {})
        abstract_methods = config.get("abstract_methods", []) or []
        module_lines = self.original_content.split("\n")

        start = min(c.lineno for c in child_nodes) - 1 if child_nodes else 0
        end = (
            max(
                (
                    c.end_lineno
                    if hasattr(c, "end_lineno") and c.end_lineno
                    else self._find_class_end(c, module_lines)
                )
                for c in child_nodes
            )
            if child_nodes
            else 0
        )

        before = "\n".join(module_lines[:start]).rstrip("\n")
        after = "\n".join(module_lines[end:]).lstrip("\n")

        base_indent = 0
        class_indent = " " * base_indent
        indent = class_indent + "    "

        abc_import_line = "from abc import ABC, abstractmethod"
        if abstract_methods:
            if abc_import_line not in before and "import abc" not in before:
                header_lines = before.split("\n") if before else []
                insert_at = 0
                for i, line in enumerate(header_lines):
                    if line.startswith("import ") or line.startswith("from "):
                        insert_at = i + 1
                header_lines.insert(insert_at, abc_import_line)
                before = "\n".join(header_lines).rstrip("\n")

        base_decl = (
            f"{class_indent}class {base_class_name}(ABC):"
            if abstract_methods
            else f"{class_indent}class {base_class_name}:"
        )
        base_lines: list[str] = [base_decl]
        base_lines.append(f'{indent}"""Base class with common functionality."""')

        all_props: set[str] = set()
        for child_config in extract_from.values():
            all_props.update(child_config.get("properties", []))
            all_props.update(child_config.get("props", []))
        if all_props:
            base_lines.append(f"{indent}def __init__(self):")
            init_indent = indent + "    "
            for prop in sorted(all_props):
                base_lines.append(f"{init_indent}self.{prop} = None")

        all_methods: set[str] = set()
        for child_config in extract_from.values():
            all_methods.update(child_config.get("methods", []))

        for method_name in sorted(all_methods):
            method_node = None
            for child in child_nodes:
                method_node = self._find_method_in_class(child, method_name)
                if method_node:
                    break
            if not method_node:
                continue
            if method_name in abstract_methods:
                base_lines.append(f"{indent}@abstractmethod")
                extracted = self._extract_method_code(method_node, indent)
                header = None
                for line in extracted.splitlines():
                    stripped = line.lstrip()
                    if stripped.startswith("def ") or stripped.startswith("async def "):
                        header = indent + stripped
                        break
                if header is None:
                    header = f"{indent}def {method_name}(self):"
                base_lines.append(header)
                base_lines.append(f"{indent}    raise NotImplementedError")
            else:
                method_code = self._extract_method_code(method_node, indent)
                if method_code.strip():
                    base_lines.append(method_code)

        base_code = "\n".join(base_lines)

        updated_children: list[str] = []
        for child_node in child_nodes:
            updated_children.append(
                f"{class_indent}class {child_node.name}({base_class_name}):"
            )
            child_doc = ast.get_docstring(child_node)
            if child_doc:
                updated_children.append(f'{indent}"""{child_doc}"""')
            updated_children.append(f"{indent}pass")

        new_block = "\n\n".join([base_code] + updated_children)

        parts: list[str] = []
        if before.strip():
            parts.append(before)
        parts.append(new_block)
        if after.strip():
            parts.append(after)
        return "\n\n".join(parts).rstrip() + "\n"

    def _build_base_class_ast(
        self,
        base_class_name: str,
        child_nodes: List[ast.ClassDef],
        extract_from: Dict[str, Dict[str, Any]],
        abstract_methods: List[str],
    ) -> ast.ClassDef:
        """Build the base class as AST node."""
        import copy

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
            method_node = self._find_method_in_class(first_child, method_name)
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
        bases = []
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

    def _update_child_class_ast(
        self,
        child_node: ast.ClassDef,
        base_class_name: str,
        child_config: Dict[str, Any],
    ) -> ast.ClassDef:
        """Update child class AST node to inherit from base and remove extracted members."""
        import copy

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
                        if _is_self_assignment_to_any(stmt, extracted_props):
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


def _is_self_assignment_to_any(stmt: ast.stmt, props: set[str]) -> bool:
    """
    Detect `self.<prop> = ...` or annotated assignment to `self.<prop>`.
    """
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
