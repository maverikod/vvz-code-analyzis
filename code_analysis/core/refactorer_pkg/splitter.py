"""
Module splitter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from .utils import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


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
    errors = []

    if not config.get("src_class"):
        errors.append("src_class not specified")

    # Extract all original members
    all_properties = set(self.extract_init_properties(src_class))
    all_methods = set()
    for item in src_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_methods.add(item.name)

    # Collect all members from destination classes
    dst_properties = set()
    dst_methods = set()
    dst_classes = config.get("dst_classes", {})

    for dst_class_name, dst_config in dst_classes.items():
        dst_properties.update(dst_config.get("props", []))
        dst_methods.update(dst_config.get("methods", []))

    # Check for missing properties
    missing_props = all_properties - dst_properties
    if missing_props:
        errors.append(f"Missing properties in split config: {missing_props}")

    # Check for missing methods (excluding special methods)
    special_methods = {"__init__", "__new__", "__del__"}
    regular_methods = all_methods - special_methods
    missing_methods = regular_methods - dst_methods
    if missing_methods:
        errors.append(f"Missing methods in split config: {missing_methods}")

    # Check for extra properties/methods in config
    extra_props = dst_properties - all_properties
    if extra_props:
        errors.append(f"Extra properties in config (not in class): {extra_props}")

    extra_methods = dst_methods - all_methods
    if extra_methods:
        errors.append(f"Extra methods in config (not in class): {extra_methods}")

    return len(errors) == 0, errors


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
        # Load file
        self.load_file()

        src_class_name = config.get("src_class")
        if not src_class_name:
            return False, "Source class name not specified in config", None

        # Find source class
        src_class = self.find_class(src_class_name)
        if not src_class:
            return False, f"Class '{src_class_name}' not found in file", None

        # Validate configuration
        is_valid, errors = self.validate_split_config(src_class, config)
        if not is_valid:
            error_msg = format_error_message(
                "config_validation", "; ".join(errors), self.file_path
            )
            return False, error_msg, None

        # Perform split to get preview
        new_content = self._perform_split(src_class, config)

        # Format preview with black (in memory)
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

        return True, None, formatted_content

    except Exception as e:
        error_msg = f"Error during preview: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None


def split_class(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Split class according to configuration."""
    try:
        # Create backup
        self.create_backup()

        # Load file
        self.load_file()

        src_class_name = config.get("src_class")
        if not src_class_name:
            return False, "Source class name not specified in config"

        # Find source class
        src_class = self.find_class(src_class_name)
        if not src_class:
            return False, f"Class '{src_class_name}' not found in file"

        # Collect original members BEFORE operation
        original_props = set(self.extract_init_properties(src_class))
        original_methods = set()
        for item in src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                original_methods.add(item.name)

        # Validate configuration
        is_valid, errors = self.validate_split_config(src_class, config)
        if not is_valid:
            error_msg = format_error_message(
                "config_validation", "; ".join(errors), self.file_path
            )
            return False, error_msg

        # Perform split
        new_content = self._perform_split(src_class, config)

        # Write new content
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Format code with black
        format_success, format_error = format_code_with_black(self.file_path)
        if not format_success:
            logger.warning(f"Code formatting failed (continuing): {format_error}")

        # Validate Python syntax
        is_valid, error_msg = self.validate_python_syntax()
        if not is_valid:
            # Restore backup
            self.restore_backup()
            return False, f"Python validation failed: {error_msg}"

        # Validate that all properties and methods are present
        is_complete, completeness_error = self.validate_completeness(
            src_class_name, config, original_props, original_methods
        )
        if not is_complete:
            # Restore backup
            self.restore_backup()
            formatted_error = format_error_message(
                "completeness", completeness_error, self.file_path
            )
            return False, formatted_error

        # Validate that all docstrings are preserved
        is_docstrings_valid, docstrings_error = self.validate_docstrings(
            src_class,
            config,
        )
        if not is_docstrings_valid:
            # Restore backup
            self.restore_backup()
            formatted_error = format_error_message(
                "docstring", docstrings_error, self.file_path
            )
            return False, formatted_error

        # Import validation is optional - dependencies might not be installed
        # Syntax check is more important and already passed
        try:
            import_valid, import_error = self.validate_imports()
            if not import_valid:
                logger.warning(f"Import validation warning: {import_error}")
        except Exception as e:
            logger.warning(f"Import validation skipped: {e}")

        return True, "Split completed successfully"

    except Exception as e:
        # Restore backup on any error
        if self.backup_path:
            self.restore_backup()
        return False, f"Error during split: {str(e)}"


def _perform_split(self, src_class: ast.ClassDef, config: Dict[str, Any]) -> str:
    """Perform the actual class splitting using AST."""
    if not self.tree:
        raise ValueError("AST tree not loaded")

    # Get configuration
    dst_classes = config.get("dst_classes", {})

    # Build mapping of what goes where
    method_mapping: Dict[str, str] = {}  # method_name -> dst_class_name
    prop_mapping: Dict[str, str] = {}  # prop_name -> dst_class_name

    for dst_class_name, dst_config in dst_classes.items():
        for method in dst_config.get("methods", []):
            method_mapping[method] = dst_class_name
        for prop in dst_config.get("props", []):
            prop_mapping[prop] = dst_class_name

    # Find source class position in module body
    src_class_idx = None
    for i, node in enumerate(self.tree.body):
        if isinstance(node, ast.ClassDef) and node.name == src_class.name:
            src_class_idx = i
            break

    if src_class_idx is None:
        raise ValueError(f"Source class {src_class.name} not found in module body")

    # Build new classes as AST nodes
    new_class_nodes = []
    for dst_class_name, dst_config in dst_classes.items():
        new_class_node = self._build_new_class_ast(
            dst_class_name,
            src_class,
            dst_config,
        )
        new_class_nodes.append(new_class_node)

    # Build modified source class as AST node
    modified_src_class_node = self._build_modified_source_class_ast(
        src_class,
        method_mapping,
        prop_mapping,
        dst_classes,
    )

    # Reconstruct module AST
    new_module_body = []
    # Add nodes before source class
    new_module_body.extend(self.tree.body[:src_class_idx])
    # Add modified source class
    new_module_body.append(modified_src_class_node)
    # Add new classes
    new_module_body.extend(new_class_nodes)
    # Add nodes after source class
    new_module_body.extend(self.tree.body[src_class_idx + 1 :])

    # Create new module and unparse
    new_module = ast.Module(body=new_module_body, type_ignores=[])
    return ast.unparse(new_module)


def _get_indent(self, line: str) -> int:
    """Get indentation level of a line."""
    return len(line) - len(line.lstrip())


def _build_new_class_ast(
    self,
    dst_class_name: str,
    src_class: ast.ClassDef,
    dst_config: Dict[str, Any],
) -> ast.ClassDef:
    """Build AST node for a new destination class."""
    # Get methods and properties for this destination class
    methods = dst_config.get("methods", [])
    props = dst_config.get("props", [])

    # Build class body
    class_body: List[ast.stmt] = []

    # Add docstring if source class has one
    if src_class.body and isinstance(src_class.body[0], ast.Expr):
        docstring = ast.get_docstring(src_class)
        if docstring:
            class_body.append(ast.Expr(ast.Constant(value=docstring)))

    # Add __init__ with properties
    if props:
        init_body: List[ast.stmt] = []
        for prop in props:
            # Create: self.prop = None
            target = ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=prop,
                ctx=ast.Store(),
            )
            assign = ast.Assign(
                targets=[target],
                value=ast.Constant(value=None),
            )
            init_body.append(assign)

        # Create __init__ method
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

    # Add methods
    for method_name in methods:
        method_node = self._find_method_in_class(src_class, method_name)
        if method_node:
            # Deep copy method node to avoid modifying original
            import copy

            new_method = copy.deepcopy(method_node)
            class_body.append(new_method)
        else:
            logger.warning(
                f"Method {method_name} not found in source class "
                f"for destination class {dst_class_name}"
            )

    # Create new class AST node
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

    # Deep copy source class to avoid modifying original
    modified_class = copy.deepcopy(src_class)

    # Get all methods and properties
    all_methods = set()
    for item in modified_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_methods.add(item.name)

    moved_methods = set(method_mapping.keys())
    all_methods - moved_methods

    # Build new class body
    new_body: List[ast.stmt] = []

    # Add docstring if present
    if modified_class.body and isinstance(modified_class.body[0], ast.Expr):
        docstring = ast.get_docstring(modified_class)
        if docstring:
            new_body.append(ast.Expr(ast.Constant(value=docstring)))

    # Build __init__ with property references
    init_body: List[ast.stmt] = []

    # Group properties by destination class
    prop_groups: Dict[str, List[str]] = {}
    for prop, dst_class in prop_mapping.items():
        if dst_class not in prop_groups:
            prop_groups[dst_class] = []
        prop_groups[dst_class].append(prop)

    # Initialize property references: self.instanceName = ClassName()
    for dst_class_name, props in prop_groups.items():
        instance_name = (
            dst_class_name[0].lower() + dst_class_name[1:]
            if dst_class_name
            else dst_class_name.lower()
        )
        # Create: self.instanceName = ClassName()
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

    # Add remaining properties from original __init__
    all_props = set(self.extract_init_properties(src_class))
    moved_props = set(prop_mapping.keys())
    remaining_props = all_props - moved_props

    # Find original __init__ to extract remaining property initializations
    original_init = self._find_method_in_class(src_class, "__init__")
    if original_init:
        for stmt in original_init.body:
            if isinstance(stmt, ast.Assign):
                # Check if this assigns a remaining property
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute):
                        if (
                            isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                            and target.attr in remaining_props
                        ):
                            init_body.append(copy.deepcopy(stmt))
                            break
            elif isinstance(stmt, ast.AnnAssign):
                if (
                    isinstance(stmt.target, ast.Attribute)
                    and isinstance(stmt.target.value, ast.Name)
                    and stmt.target.value.id == "self"
                    and stmt.target.attr in remaining_props
                ):
                    init_body.append(copy.deepcopy(stmt))

    # Create __init__ method
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

    # Add wrapper methods for moved methods
    for method_name, dst_class_name in method_mapping.items():
        original_method = self._find_method_in_class(src_class, method_name)
        if original_method:
            # Create wrapper method that calls destination class method
            dst_var = (
                dst_class_name[0].lower() + dst_class_name[1:]
                if dst_class_name
                else dst_class_name.lower()
            )

            # Build call: self.dstVar.method_name(*args, **kwargs)
            call_args = []
            if isinstance(original_method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Extract method arguments (skip self)
                for arg in original_method.args.args[1:]:  # Skip self
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

            # Create wrapper method
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

    # Add remaining methods (not moved)
    for item in modified_class.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name not in moved_methods and item.name != "__init__":
                new_body.append(item)

    # Update class body
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

    # Add docstring
    docstring = ast.get_docstring(src_class)
    if docstring:
        lines.append(f'{indent}"""{docstring}"""')

    # Add __init__ with property references
    lines.append(f"{indent}def __init__(self):")
    init_indent = indent + "    "
    init_has_body = False  # Track if __init__ body has content

    # Group properties by destination class
    prop_groups: Dict[str, List[str]] = {}
    for prop, dst_class in prop_mapping.items():
        if dst_class not in prop_groups:
            prop_groups[dst_class] = []
        prop_groups[dst_class].append(prop)

    # Initialize property references
    for dst_class_name, props in prop_groups.items():
        # Convert class name to instance variable name (camelCase)
        instance_name = (
            dst_class_name[0].lower() + dst_class_name[1:]
            if dst_class_name
            else dst_class_name.lower()
        )
        lines.append(f"{init_indent}self.{instance_name} = {dst_class_name}()")
        init_has_body = True

    # Add remaining properties (not in any dst class)
    all_props = set(self.extract_init_properties(src_class))
    moved_props = set(prop_mapping.keys())
    remaining_props = all_props - moved_props

    # Find original __init__ to get property initializations
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
            # Check if this line initializes a remaining property
            for prop in remaining_props:
                if f"self.{prop}" in line and "=" in line:
                    # Adjust indentation
                    original_indent = len(line) - len(line.lstrip())
                    new_indent = init_indent + " " * (
                        original_indent - (init_method.lineno - 1)
                    )
                    lines.append(new_indent + line.lstrip())
                    init_has_body = True
                    break

    # Ensure __init__ has at least pass if empty body
    if not init_has_body:
        lines.append(f"{init_indent}pass")

    # Add wrapper methods
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

    # Add wrapper methods for moved methods
    for method_name, dst_class_name in method_mapping.items():
        wrapper = self._create_method_wrapper(method_name, dst_class_name, indent)
        lines.append(wrapper)

    return "\n".join(lines)


def _create_method_wrapper(
    self, method_name: str, dst_class_name: str, indent: str
) -> str:
    """Create a wrapper method that delegates to the destination class."""
    # Get original method signature from source class
    method_node = None
    if self.tree:
        # Find source class first
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Check if this class has the method
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
        # Extract arguments
        args = [arg.arg for arg in method_node.args.args]
        if args and args[0] == "self":
            args = args[1:]

        args_str = ", ".join(["self"] + args)
        # Convert class name to instance variable name (camelCase)
        dst_var = (
            dst_class_name[0].lower() + dst_class_name[1:]
            if dst_class_name
            else dst_class_name.lower()
        )

        # Build call arguments
        call_args = ", ".join(args) if args else ""

        wrapper_lines = [
            f"{indent}def {method_name}({args_str}):",
            f"{indent}    return self.{dst_var}.{method_name}({call_args})",
        ]

        # Handle async methods
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
    try:
        # Reload file to get new AST
        with open(self.file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(self.file_path))

        # Find source class in new tree
        new_src_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == src_class_name:
                new_src_class = node
                break

        if not new_src_class:
            return False, f"Source class '{src_class_name}' not found after split"

        # Find all destination classes
        dst_classes = {}
        for dst_class_name in config.get("dst_classes", {}).keys():
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                    dst_classes[dst_class_name] = node
                    break

        # Collect properties and methods from new classes
        new_props = set()
        new_methods = set()

        # From source class (remaining + property references)
        new_src_props = set(self.extract_init_properties(new_src_class))
        new_props.update(new_src_props)

        # Check for property references (dst_class_name.lower() attributes)
        for item in new_src_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    # This is a property reference
                                    new_props.add(target.attr)

        # From destination classes
        for dst_class_name, dst_class_node in dst_classes.items():
            dst_props = set(self.extract_init_properties(dst_class_node))
            new_props.update(dst_props)

            for item in dst_class_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    new_methods.add(item.name)

        # From source class methods (wrappers + remaining)
        for item in new_src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_methods.add(item.name)

        # Validate properties - strict check
        missing_props = original_props - new_props
        if missing_props:
            return (
                False,
                f"Missing properties after split: {missing_props}. "
                f"Original: {len(original_props)}, Found: {len(new_props)}",
            )

        # Validate methods (excluding special methods) - strict check
        special_methods = {"__init__", "__new__", "__del__"}
        regular_original = original_methods - special_methods
        regular_new = new_methods - special_methods
        missing_methods = regular_original - regular_new
        if missing_methods:
            return (
                False,
                f"Missing methods after split: {missing_methods}. "
                f"Original: {len(regular_original)}, Found: {len(regular_new)}",
            )

        return True, None

    except Exception as e:
        return False, f"Error during completeness validation: {str(e)}"


def validate_docstrings(
    self,
    src_class: ast.ClassDef,
    config: Dict[str, Any],
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
        # Reload file to get new AST
        with open(self.file_path, "r", encoding="utf-8") as f:
            new_content = f.read()
        new_tree = ast.parse(new_content, filename=str(self.file_path))

        # Get source class docstring
        src_class_docstring = ast.get_docstring(src_class)

        # Get all method docstrings from source class
        src_method_docstrings = {}
        for item in src_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_docstring = ast.get_docstring(item)
                if method_docstring:
                    src_method_docstrings[item.name] = method_docstring

        # Find all destination classes
        dst_classes = {}
        dst_classes_config = config.get("dst_classes", {})
        for dst_class_name in dst_classes_config.keys():
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == dst_class_name:
                    dst_classes[dst_class_name] = node
                    break

        # Check class docstring in destination classes
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
                return False, (
                    f"Class docstring not found in destination classes. "
                    f"Expected: {src_class_docstring[:50]}..."
                )

        # Check method docstrings in destination classes
        method_mapping: Dict[str, str] = {}  # method_name -> dst_class_name
        for dst_class_name, dst_config in dst_classes_config.items():
            for method in dst_config.get("methods", []):
                method_mapping[method] = dst_class_name

        for method_name, method_docstring in src_method_docstrings.items():
            if method_name in method_mapping:
                dst_class_name = method_mapping[method_name]
                dst_class_node = dst_classes.get(dst_class_name)

                if not dst_class_node:
                    return False, (
                        f"Destination class '{dst_class_name}' not found "
                        f"for method '{method_name}'"
                    )

                # Find method in destination class
                method_found = False
                for item in dst_class_node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        dst_method_docstring = ast.get_docstring(item)
                        if not dst_method_docstring:
                            return False, (
                                f"Method '{method_name}' docstring missing "
                                f"in destination class '{dst_class_name}'. "
                                f"Expected: {method_docstring[:50]}..."
                            )
                        if dst_method_docstring.strip() != method_docstring.strip():
                            return False, (
                                f"Method '{method_name}' docstring mismatch "
                                f"in destination class '{dst_class_name}'. "
                                f"Expected: {method_docstring[:50]}..., "
                                f"Got: {dst_method_docstring[:50]}..."
                            )
                        method_found = True
                        break

                if not method_found:
                    return False, (
                        f"Method '{method_name}' not found "
                        f"in destination class '{dst_class_name}'"
                    )

        return True, None

    except Exception as e:
        return False, f"Error during docstring validation: {str(e)}"
