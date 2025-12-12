"""
Code refactoring module for class splitting.

This module provides functionality to split large classes into smaller ones
with safety checks and rollback capabilities.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ClassSplitter:
    """Class for splitting classes into smaller components."""

    def __init__(self, file_path: Path) -> None:
        """Initialize class splitter."""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        self.backup_path: Optional[Path] = None
        self.original_content: str = ""
        self.tree: Optional[ast.Module] = None

    def create_backup(self) -> Path:
        """Create backup copy of the file."""
        backup_dir = self.file_path.parent / ".code_mapper_backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = int(Path(self.file_path).stat().st_mtime)
        backup_path = (
            backup_dir / f"{self.file_path.stem}_{timestamp}.py.backup"
        )
        shutil.copy2(self.file_path, backup_path)
        self.backup_path = backup_path
        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def restore_backup(self) -> None:
        """Restore file from backup."""
        if self.backup_path and self.backup_path.exists():
            shutil.copy2(self.backup_path, self.file_path)
            logger.info(f"File restored from backup: {self.backup_path}")

    def load_file(self) -> None:
        """Load and parse file content."""
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.original_content = f.read()
        self.tree = ast.parse(
            self.original_content, filename=str(self.file_path)
        )

    def find_class(self, class_name: str) -> Optional[ast.ClassDef]:
        """Find class definition in AST."""
        if not self.tree:
            return None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

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

    def extract_init_properties(self, class_node: ast.ClassDef) -> List[str]:
        """Extract properties initialized in __init__."""
        properties = []
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    # Handle regular assignments: self.attr = value
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    properties.append(target.attr)
                    # Handle annotated assignments: self.attr: Type = value
                    elif isinstance(stmt, ast.AnnAssign):
                        if isinstance(stmt.target, ast.Attribute):
                            if (
                                isinstance(stmt.target.value, ast.Name)
                                and stmt.target.value.id == "self"
                            ):
                                properties.append(stmt.target.attr)
        return properties

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
                return False, f"Configuration validation failed: {'; '.join(errors)}"

            # Perform split
            new_content = self._perform_split(src_class, config)

            # Write new content
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

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
                return False, f"Completeness validation failed: {completeness_error}"

            # Validate that all docstrings are preserved
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                src_class, config
            )
            if not is_docstrings_valid:
                # Restore backup
                self.restore_backup()
                return False, f"Docstring validation failed: {docstrings_error}"

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
        """Perform the actual class splitting."""
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

        # Find source class position in module
        lines = self.original_content.split("\n")
        src_class_start = src_class.lineno - 1
        src_class_end = self._find_class_end(src_class, lines)

        # Extract class content
        class_lines = lines[src_class_start:src_class_end]
        class_indent = self._get_indent(class_lines[0])

        # Build new classes
        new_classes = []
        for dst_class_name, dst_config in dst_classes.items():
            new_class_code = self._build_new_class(
                dst_class_name,
                src_class,
                dst_config,
                class_indent,
            )
            new_classes.append(new_class_code)

        # Build modified source class
        modified_src_class = self._build_modified_source_class(
            src_class,
            method_mapping,
            prop_mapping,
            dst_classes,
            class_indent,
        )

        # Reconstruct file
        result_lines = []
        result_lines.extend(lines[:src_class_start])
        result_lines.append(modified_src_class)
        result_lines.extend(new_classes)
        result_lines.extend(lines[src_class_end:])

        return "\n".join(result_lines)

    def _find_class_end(self, class_node: ast.ClassDef, lines: List[str]) -> int:
        """Find the end line of a class definition."""
        # Find the last line of the class body
        if class_node.body:
            last_stmt = class_node.body[-1]
            # Get the end line of the last statement
            if hasattr(last_stmt, "end_lineno") and last_stmt.end_lineno:
                return last_stmt.end_lineno
            else:
                # Fallback: find next class/function at same or less indentation
                class_indent = len(lines[class_node.lineno - 1]) - len(
                    lines[class_node.lineno - 1].lstrip()
                )
                for i in range(last_stmt.lineno, len(lines)):
                    line = lines[i]
                    if line.strip() and not line.strip().startswith("#"):
                        indent = len(line) - len(line.lstrip())
                        if indent <= class_indent:
                            return i
                return len(lines)
        return class_node.lineno

    def _get_indent(self, line: str) -> int:
        """Get indentation level of a line."""
        return len(line) - len(line.lstrip())

    def _build_new_class(
        self,
        dst_class_name: str,
        src_class: ast.ClassDef,
        dst_config: Dict[str, Any],
        base_indent: int,
    ) -> str:
        """Build code for a new destination class."""
        indent = " " * base_indent
        lines = [f"{indent}class {dst_class_name}:"]
        indent += "    "

        # Add docstring if source class has one
        if src_class.body and isinstance(src_class.body[0], ast.Expr):
            docstring = ast.get_docstring(src_class)
            if docstring:
                lines.append(f'{indent}"""{docstring}"""')

        # Add __init__ with properties
        props = dst_config.get("props", [])
        if props:
            lines.append(f"{indent}def __init__(self):")
            init_indent = indent + "    "
            for prop in props:
                lines.append(f"{init_indent}self.{prop} = None")

        # Add methods
        methods = dst_config.get("methods", [])
        for method_name in methods:
            method_node = self._find_method_in_class(src_class, method_name)
            if method_node:
                method_code = self._extract_method_code(method_node, indent)
                if method_code.strip():
                    lines.append(method_code)
                else:
                    logger.warning(
                        f"Could not extract code for method {method_name} "
                        f"in class {dst_class_name}"
                    )
            else:
                logger.warning(
                    f"Method {method_name} not found in source class "
                    f"for destination class {dst_class_name}"
                )

        return "\n".join(lines)

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

    def _extract_method_code(self, method_node: Any, indent: str) -> str:
        """Extract method code as string with proper indentation, including comments."""
        # Get method lines from original content
        lines = self.original_content.split("\n")
        method_start_line = method_node.lineno - 1

        # Find method end - use end_lineno if available,
        # otherwise find by indentation
        if hasattr(method_node, "end_lineno") and method_node.end_lineno:
            method_end = method_node.end_lineno
        else:
            # Fallback: find next statement at same or less indentation
            method_indent = len(lines[method_start_line]) - len(lines[method_start_line].lstrip())
            method_end = method_start_line + 1
            for i in range(method_start_line + 1, len(lines)):
                line = lines[i]
                if line.strip() and not line.strip().startswith("#"):
                    line_indent = len(line) - len(line.lstrip())
                    if line_indent <= method_indent:
                        method_end = i
                        break
                method_end = i + 1

        # Find comments before method (on same or higher indentation level)
        # Look backwards from method start to find preceding comments
        method_indent = len(lines[method_start_line]) - len(lines[method_start_line].lstrip())
        actual_start = method_start_line
        
        # Look backwards for comments and empty lines
        for i in range(method_start_line - 1, -1, -1):
            line = lines[i]
            if not line.strip():
                # Empty line - continue looking
                continue
            elif line.strip().startswith("#"):
                # Comment line - check if it's at same or less indentation
                comment_indent = len(line) - len(line.lstrip())
                if comment_indent <= method_indent:
                    # This comment belongs to the method
                    actual_start = i
                else:
                    # Comment is more indented, might be part of previous method
                    break
            else:
                # Non-comment, non-empty line - stop here
                break

        method_lines = lines[actual_start:method_end]

        # Adjust indentation
        if method_lines:
            # Find first non-empty line for base indent
            original_indent = 0
            for line in method_lines:
                if line.strip():
                    original_indent = len(line) - len(line.lstrip())
                    break

            adjusted_lines = []
            for line in method_lines:
                if line.strip():
                    current_indent = len(line) - len(line.lstrip())
                    indent_diff = current_indent - original_indent
                    new_indent = indent + " " * indent_diff
                    adjusted_lines.append(new_indent + line.lstrip())
                else:
                    adjusted_lines.append("")

            result = "\n".join(adjusted_lines)
            if result.strip():
                return result
        return ""

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
            instance_name = dst_class_name[0].lower() + dst_class_name[1:] if dst_class_name else dst_class_name.lower()
            lines.append(
                f"{init_indent}self.{instance_name} = {dst_class_name}()"
            )
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
            dst_var = dst_class_name[0].lower() + dst_class_name[1:] if dst_class_name else dst_class_name.lower()

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

    def validate_python_syntax(self) -> tuple[bool, Optional[str]]:
        """Validate Python syntax of modified file."""
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", str(self.file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, result.stderr
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Syntax validation timeout"
        except Exception as e:
            return False, str(e)

    def validate_imports(self) -> tuple[bool, Optional[str]]:
        """Try to import the modified module."""
        try:
            # Create temporary file with modified content
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as temp_file:
                shutil.copy2(self.file_path, temp_file.name)

                # Try to import
                import sys

                sys.path.insert(0, str(self.file_path.parent))
                module_name = self.file_path.stem
                try:
                    if module_name in sys.modules:
                        del sys.modules[module_name]
                    __import__(module_name)
                    return True, None
                except ImportError as e:
                    return False, str(e)
                finally:
                    sys.path.remove(str(self.file_path.parent))
                    if module_name in sys.modules:
                        del sys.modules[module_name]

        except Exception as e:
            return False, str(e)

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
                    if dst_docstring and dst_docstring.strip() == src_class_docstring.strip():
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


class SuperclassExtractor:
    """Class for extracting common functionality into base class."""

    def __init__(self, file_path: Path) -> None:
        """Initialize superclass extractor."""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        self.backup_path: Optional[Path] = None
        self.original_content: str = ""
        self.tree: Optional[ast.Module] = None

    def create_backup(self) -> Path:
        """Create backup copy of the file."""
        backup_dir = self.file_path.parent / ".code_mapper_backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = int(Path(self.file_path).stat().st_mtime)
        backup_path = (
            backup_dir / f"{self.file_path.stem}_{timestamp}.py.backup"
        )
        shutil.copy2(self.file_path, backup_path)
        self.backup_path = backup_path
        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def restore_backup(self) -> None:
        """Restore file from backup."""
        if self.backup_path and self.backup_path.exists():
            shutil.copy2(self.backup_path, self.file_path)
            logger.info(f"File restored from backup: {self.backup_path}")

    def load_file(self) -> None:
        """Load and parse file content."""
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.original_content = f.read()
        self.tree = ast.parse(
            self.original_content, filename=str(self.file_path)
        )

    def find_class(self, class_name: str) -> Optional[ast.ClassDef]:
        """Find class definition in AST."""
        if not self.tree:
            return None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def get_class_bases(self, class_node: ast.ClassDef) -> List[str]:
        """Get list of base class names."""
        bases = []
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle qualified names like module.Class
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
            return False, "AST tree not loaded"

        # Collect all base classes for child classes
        all_bases: Dict[str, List[str]] = {}
        for child_name in child_classes:
            child_node = self.find_class(child_name)
            if child_node:
                bases = self.get_class_bases(child_node)
                all_bases[child_name] = bases

        # Check if any child already has a base class
        conflicts = []
        for child_name, bases in all_bases.items():
            if bases:
                conflicts.append(f"{child_name} already inherits from {bases}")

        if conflicts:
            return False, f"Multiple inheritance conflicts: {'; '.join(conflicts)}"

        # Check for diamond problem potential
        # (simplified check - could be enhanced)

        return True, None

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
            return True, None  # Method doesn't exist, no conflict

        if len(methods) != len(class_names):
            return (
                False,
                f"Method {method_name} not found in all classes",
            )

        # Check if all methods have same signature
        first_method = methods[0]
        first_args = [arg.arg for arg in first_method.args.args]
        first_returns = self._get_return_type(first_method)

        for i, method in enumerate(methods[1:], 1):
            args = [arg.arg for arg in method.args.args]
            returns = self._get_return_type(method)

            if args != first_args:
                return (
                    False,
                    f"Method {method_name} has incompatible signatures "
                    f"in class {class_names[i]}",
                )

            if returns != first_returns:
                return (
                    False,
                    f"Method {method_name} has incompatible return types "
                    f"in class {class_names[i]}",
                )

        return True, None

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

    def extract_init_properties(self, class_node: ast.ClassDef) -> List[str]:
        """Extract properties initialized in __init__."""
        properties = []
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    # Handle regular assignments: self.attr = value
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    properties.append(target.attr)
                    # Handle annotated assignments: self.attr: Type = value
                    elif isinstance(stmt, ast.AnnAssign):
                        if isinstance(stmt.target, ast.Attribute):
                            if (
                                isinstance(stmt.target.value, ast.Name)
                                and stmt.target.value.id == "self"
                            ):
                                properties.append(stmt.target.attr)
        return properties

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate extraction configuration."""
        errors = []

        base_class = config.get("base_class")
        if not base_class:
            errors.append("base_class not specified")

        child_classes = config.get("child_classes", [])
        if not child_classes:
            errors.append("child_classes list is empty")

        extract_from = config.get("extract_from", {})
        if not extract_from:
            errors.append("extract_from configuration is empty")

        # Check that all child classes are in extract_from
        for child in child_classes:
            if child not in extract_from:
                errors.append(f"Child class '{child}' not in extract_from")

        # Check that base_class doesn't already exist
        if self.find_class(base_class):
            errors.append(f"Base class '{base_class}' already exists")

        return len(errors) == 0, errors

    def extract_superclass(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Extract common functionality into base class."""
        try:
            # Create backup
            self.create_backup()

            # Load file
            self.load_file()

            # Validate configuration
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                return False, f"Configuration validation failed: {'; '.join(errors)}"

            base_class_name = config.get("base_class")
            child_classes = config.get("child_classes", [])

            # Check for multiple inheritance conflicts
            conflict_valid, conflict_error = self.check_multiple_inheritance_conflicts(
                child_classes, base_class_name
            )
            if not conflict_valid:
                return False, conflict_error

            # Find all child class nodes
            child_nodes = []
            for child_name in child_classes:
                child_node = self.find_class(child_name)
                if not child_node:
                    return False, f"Child class '{child_name}' not found"
                child_nodes.append(child_node)

            # Check method compatibility
            abstract_methods = config.get("abstract_methods", [])

            # Check all methods that will be extracted
            all_methods = set()
            extract_from = config.get("extract_from", {})
            for child_config in extract_from.values():
                all_methods.update(child_config.get("methods", []))

            for method_name in all_methods:
                is_compatible, error = self.check_method_compatibility(
                    child_classes, method_name
                )
                if not is_compatible:
                    return False, error

            # Perform extraction
            new_content = self._perform_extraction(config, child_nodes)

            # Write new content
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Validate Python syntax
            is_valid, error_msg = self.validate_python_syntax()
            if not is_valid:
                # Restore backup
                self.restore_backup()
                return False, f"Python validation failed: {error_msg}"

            # Validate completeness
            is_complete, completeness_error = self.validate_completeness(
                base_class_name, child_classes, config
            )
            if not is_complete:
                # Restore backup
                self.restore_backup()
                return False, f"Completeness validation failed: {completeness_error}"

            # Validate that all docstrings are preserved
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                child_nodes, config
            )
            if not is_docstrings_valid:
                # Restore backup
                self.restore_backup()
                return False, f"Docstring validation failed: {docstrings_error}"

            # Try to import the module (skip if dependencies are missing)
            try:
                import_valid, import_error = self.validate_imports()
                if not import_valid:
                    logger.warning(f"Import validation warning: {import_error}")
            except Exception as e:
                logger.warning(f"Import validation skipped: {e}")

            return True, "Superclass extraction completed successfully"

        except Exception as e:
            # Restore backup on any error
            if self.backup_path:
                self.restore_backup()
            return False, f"Error during extraction: {str(e)}"

    def _perform_extraction(
        self, config: Dict[str, Any], child_nodes: List[ast.ClassDef]
    ) -> str:
        """Perform the actual superclass extraction."""
        if not self.tree:
            raise ValueError("AST tree not loaded")

        base_class_name = config.get("base_class")
        extract_from = config.get("extract_from", {})
        abstract_methods = config.get("abstract_methods", [])

        # Check if abc import is needed
        has_abc_import = False
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == "abc":
                has_abc_import = True
                break
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "abc":
                        has_abc_import = True
                        break

        # Build base class
        base_class_code = self._build_base_class(
            base_class_name, child_nodes, extract_from, abstract_methods
        )

        # Update child classes to inherit from base
        lines = self.original_content.split("\n")
        updated_lines = lines.copy()

        # Find positions of child classes
        class_positions = {}
        for child_node in child_nodes:
            class_positions[child_node.name] = child_node.lineno - 1

        # Update each child class (process in reverse to preserve line numbers)
        child_updates = []
        for child_node in child_nodes:
            child_name = child_node.name
            child_config = extract_from.get(child_name, {})
            child_start = child_node.lineno - 1
            child_end = self._find_class_end(child_node, lines)

            # Build updated child class
            updated_child = self._update_child_class(
                child_node, base_class_name, child_config, lines
            )

            child_updates.append((child_start, child_end, updated_child))
        
        # Apply updates in reverse order
        for child_start, child_end, updated_child in sorted(child_updates, reverse=True):
            # Replace in lines
            updated_lines[child_start:child_end] = [updated_child]

        # Insert base class before first child class
        first_child_pos = min(class_positions.values())
        updated_lines.insert(first_child_pos, base_class_code)

        # Add ABC import if needed and not present
        if abstract_methods and not has_abc_import:
            # Find last import line
            last_import = -1
            for i, line in enumerate(updated_lines):
                if line.strip().startswith("import ") or line.strip().startswith("from "):
                    last_import = i
            # Insert after last import
            if last_import >= 0:
                updated_lines.insert(last_import + 1, "from abc import ABC, abstractmethod")
            else:
                updated_lines.insert(0, "from abc import ABC, abstractmethod")

        return "\n".join(updated_lines)

    def _build_base_class(
        self,
        base_class_name: str,
        child_nodes: List[ast.ClassDef],
        extract_from: Dict[str, Dict[str, Any]],
        abstract_methods: List[str],
    ) -> str:
        """Build the base class code."""
        lines = []
        # Check if ABC import is needed
        needs_abc = bool(abstract_methods)
        if needs_abc:
            lines.append(f"class {base_class_name}(ABC):")
        else:
            lines.append(f"class {base_class_name}:")
        lines.append('    """Base class with common functionality."""')
        lines.append("")

        # Add properties
        all_props = set()
        for child_config in extract_from.values():
            # Support both "properties" and "props" keys
            all_props.update(child_config.get("properties", []))
            all_props.update(child_config.get("props", []))

        if all_props:
            lines.append("    def __init__(self):")
            for prop in sorted(all_props):
                lines.append(f"        self.{prop} = None")
            lines.append("")

        # Add methods
        all_methods = set()
        for child_config in extract_from.values():
            all_methods.update(child_config.get("methods", []))

        # Get method implementations from first child
        first_child = child_nodes[0]
        for method_name in sorted(all_methods):
            method_node = self._find_method_in_class(first_child, method_name)
            if method_node:
                if method_name in abstract_methods:
                    # Create abstract method
                    args = [arg.arg for arg in method_node.args.args]
                    args_str = ", ".join(args)
                    is_async = isinstance(method_node, ast.AsyncFunctionDef)
                    async_prefix = "async " if is_async else ""
                    lines.append(f"    @abstractmethod")
                    lines.append(f"    {async_prefix}def {method_name}({args_str}):")
                    lines.append(f"        raise NotImplementedError")
                    lines.append("")
                else:
                    # Extract full method
                    method_code = self._extract_method_code(method_node, "    ")
                    lines.append(method_code)
                    lines.append("")

        return "\n".join(lines)

    def _update_child_class(
        self,
        child_node: ast.ClassDef,
        base_class_name: str,
        child_config: Dict[str, Any],
        lines: List[str],
    ) -> str:
        """Update child class to inherit from base and remove extracted members."""
        child_start = child_node.lineno - 1
        child_end = self._find_class_end(child_node, lines)
        child_lines = lines[child_start:child_end]

        # Update class definition to inherit from base
        class_line = child_lines[0]
        if "(" in class_line:
            # Already has bases, add to them
            class_line = class_line.replace("(", f"({base_class_name}, ")
        else:
            class_line = class_line.replace(":", f"({base_class_name}):")

        # Remove extracted methods and properties
        extracted_methods = set(child_config.get("methods", []))
        # Support both "properties" and "props" keys
        extracted_props = set(child_config.get("properties", []))
        extracted_props.update(child_config.get("props", []))

        # Parse to find method boundaries
        child_tree = ast.parse("\n".join(child_lines))
        child_ast = child_tree.body[0] if child_tree.body else None
        
        if not child_ast:
            return class_line + "\n    pass\n"

        # Build result by including non-extracted items
        result_lines = [class_line]
        
        # Add docstring if present
        if child_ast.body and isinstance(child_ast.body[0], ast.Expr):
            docstring = ast.get_docstring(child_ast)
            if docstring:
                result_lines.append(f'    """{docstring}"""')
        
        # Process each body item
        for item in child_ast.body:
            if isinstance(item, ast.Expr):
                # Docstring already handled
                continue
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == "__init__":
                    # Keep __init__ but remove extracted properties
                    method_code = self._extract_method_code(item, "    ")
                    if method_code.strip():
                        # Remove lines with extracted properties
                        method_lines = method_code.split("\n")
                        filtered_lines = []
                        def_line_found = False
                        for line in method_lines:
                            if "def __init__" in line:
                                def_line_found = True
                                filtered_lines.append(line)
                                continue
                            # Check if line assigns extracted property
                            should_skip = False
                            if "self." in line and "=" in line:
                                for prop in extracted_props:
                                    # Check if this line assigns self.prop
                                    # Look for pattern: self.prop = ... (with proper spacing)
                                    stripped = line.strip()
                                    # Match: self.prop = or self.prop=
                                    prop_pattern = f"self.{prop}"
                                    if stripped.startswith(prop_pattern):
                                        # Check what comes after prop name
                                        after_prop = stripped[len(prop_pattern):].lstrip()
                                        if after_prop.startswith("="):
                                            should_skip = True
                                            break
                            if not should_skip:
                                filtered_lines.append(line)
                        
                        # Ensure __init__ has at least pass if empty body
                        # Check if there's any body after def line
                        has_body = False
                        for line in filtered_lines:
                            if "def __init__" in line:
                                continue
                            if line.strip() and not line.strip().startswith('"""'):
                                has_body = True
                                break
                        
                        if not has_body and def_line_found:
                            # Add pass after def line
                            for i, line in enumerate(filtered_lines):
                                if "def __init__" in line:
                                    # Calculate proper indent for pass
                                    def_indent = len(line) - len(line.lstrip())
                                    pass_indent = " " * (def_indent + 4)
                                    # Insert pass right after def line
                                    # Make sure we don't insert in the middle of a multi-line def
                                    insert_pos = i + 1
                                    # Skip any docstring or empty lines immediately after def
                                    while insert_pos < len(filtered_lines) and (
                                        not filtered_lines[insert_pos].strip() or
                                        filtered_lines[insert_pos].strip().startswith('"""')
                                    ):
                                        insert_pos += 1
                                    filtered_lines.insert(insert_pos, f"{pass_indent}pass")
                                    break
                        
                        if filtered_lines:
                            result_lines.append("\n".join(filtered_lines))
                elif item.name not in extracted_methods:
                    # Include this method
                    method_code = self._extract_method_code(item, "    ")
                    if method_code.strip():
                        result_lines.append(method_code)

        # Ensure class has at least pass if empty
        if len(result_lines) == 1 or (len(result_lines) == 2 and result_lines[1].strip().startswith('"""')):
            result_lines.append("    pass")

        return "\n".join(result_lines)


    def _extract_method_code(self, method_node: Any, indent: str) -> str:
        """Extract method code as string with proper indentation, including comments."""
        lines = self.original_content.split("\n")
        method_start_line = method_node.lineno - 1

        # Find method end - use end_lineno if available,
        # otherwise find by indentation
        if hasattr(method_node, "end_lineno") and method_node.end_lineno:
            method_end = method_node.end_lineno
        else:
            # Fallback: find next statement at same or less indentation
            method_indent = len(lines[method_start_line]) - len(lines[method_start_line].lstrip())
            method_end = method_start_line + 1
            for i in range(method_start_line + 1, len(lines)):
                line = lines[i]
                if line.strip() and not line.strip().startswith("#"):
                    line_indent = len(line) - len(line.lstrip())
                    if line_indent <= method_indent:
                        method_end = i
                        break
                method_end = i + 1

        # Find comments before method (on same or higher indentation level)
        method_indent = len(lines[method_start_line]) - len(lines[method_start_line].lstrip())
        actual_start = method_start_line
        
        # Look backwards for comments and empty lines
        for i in range(method_start_line - 1, -1, -1):
            line = lines[i]
            if not line.strip():
                # Empty line - continue looking
                continue
            elif line.strip().startswith("#"):
                # Comment line - check if it's at same or less indentation
                comment_indent = len(line) - len(line.lstrip())
                if comment_indent <= method_indent:
                    # This comment belongs to the method
                    actual_start = i
                else:
                    # Comment is more indented, might be part of previous method
                    break
            else:
                # Non-comment, non-empty line - stop here
                break

        method_lines = lines[actual_start:method_end]

        if method_lines:
            # Find first non-empty line for base indent
            original_indent = 0
            for line in method_lines:
                if line.strip():
                    original_indent = len(line) - len(line.lstrip())
                    break

            adjusted_lines = []
            for line in method_lines:
                if line.strip():
                    current_indent = len(line) - len(line.lstrip())
                    new_indent = indent + " " * (current_indent - original_indent)
                    adjusted_lines.append(new_indent + line.lstrip())
                else:
                    adjusted_lines.append("")
            return "\n".join(adjusted_lines)
        return ""

    def _find_class_end(self, class_node: ast.ClassDef, lines: List[str]) -> int:
        """Find the end line of a class definition."""
        if class_node.body:
            last_stmt = class_node.body[-1]
            if hasattr(last_stmt, "end_lineno") and last_stmt.end_lineno:
                return last_stmt.end_lineno
            else:
                class_indent = len(lines[class_node.lineno - 1]) - len(
                    lines[class_node.lineno - 1].lstrip()
                )
                for i in range(last_stmt.lineno, len(lines)):
                    line = lines[i]
                    if line.strip() and not line.strip().startswith("#"):
                        indent = len(line) - len(line.lstrip())
                        if indent <= class_indent:
                            return i
                return len(lines)
        return class_node.lineno

    def validate_python_syntax(self) -> tuple[bool, Optional[str]]:
        """Validate Python syntax of modified file."""
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", str(self.file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, result.stderr
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Syntax validation timeout"
        except Exception as e:
            return False, str(e)

    def validate_imports(self) -> tuple[bool, Optional[str]]:
        """Try to import the modified module."""
        try:
            import sys

            sys.path.insert(0, str(self.file_path.parent))
            module_name = self.file_path.stem
            try:
                if module_name in sys.modules:
                    del sys.modules[module_name]
                __import__(module_name)
                return True, None
            except ImportError as e:
                return False, str(e)
            finally:
                sys.path.remove(str(self.file_path.parent))
                if module_name in sys.modules:
                    del sys.modules[module_name]

        except Exception as e:
            return False, str(e)

    def validate_completeness(
        self,
        base_class_name: str,
        child_classes: List[str],
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str]]:
        """Validate that all members are present after extraction."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))

            # Find base class
            base_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                    base_class = node
                    break

            if not base_class:
                return False, f"Base class '{base_class_name}' not found"

            # Validate that all extracted members are in base class
            extract_from = config.get("extract_from", {})
            all_extracted_methods = set()
            all_extracted_props = set()

            for child_config in extract_from.values():
                all_extracted_methods.update(child_config.get("methods", []))
                # Support both "properties" and "props" keys
                all_extracted_props.update(child_config.get("properties", []))
                all_extracted_props.update(child_config.get("props", []))

            base_methods = set()
            for item in base_class.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    base_methods.add(item.name)

            base_props = set(self.extract_init_properties(base_class))

            missing_methods = all_extracted_methods - base_methods
            if missing_methods:
                return False, f"Missing methods in base class: {missing_methods}"

            missing_props = all_extracted_props - base_props
            if missing_props:
                return False, f"Missing properties in base class: {missing_props}"

            return True, None

        except Exception as e:
            return False, f"Error during completeness validation: {str(e)}"

    def validate_docstrings(
        self,
        child_nodes: List[ast.ClassDef],
        config: Dict[str, Any],
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
            # Reload file to get new AST
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))

            base_class_name = config.get("base_class")
            extract_from = config.get("extract_from", {})

            # Find base class
            base_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                    base_class = node
                    break

            if not base_class:
                return False, f"Base class '{base_class_name}' not found after extraction"

            # Check child class docstrings are preserved
            for child_node in child_nodes:
                child_name = child_node.name
                child_config = extract_from.get(child_name, {})
                
                # Find child class in new tree
                new_child_class = None
                for node in ast.walk(new_tree):
                    if isinstance(node, ast.ClassDef) and node.name == child_name:
                        new_child_class = node
                        break

                if not new_child_class:
                    return False, f"Child class '{child_name}' not found after extraction"

                # Check child class docstring
                original_child_docstring = ast.get_docstring(child_node)
                if original_child_docstring:
                    new_child_docstring = ast.get_docstring(new_child_class)
                    if not new_child_docstring:
                        return False, (
                            f"Child class '{child_name}' docstring missing. "
                            f"Expected: {original_child_docstring[:50]}..."
                        )
                    if new_child_docstring.strip() != original_child_docstring.strip():
                        return False, (
                            f"Child class '{child_name}' docstring mismatch. "
                            f"Expected: {original_child_docstring[:50]}..., "
                            f"Got: {new_child_docstring[:50]}..."
                        )

                # Check method docstrings in base class
                extracted_methods = set(child_config.get("methods", []))
                for method_name in extracted_methods:
                    # Find method in original child class
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
                            # Check method docstring in base class
                            base_method = None
                            for item in base_class.body:
                                if (
                                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                                    and item.name == method_name
                                ):
                                    base_method = item
                                    break

                            if not base_method:
                                return False, (
                                    f"Method '{method_name}' not found "
                                    f"in base class '{base_class_name}'"
                                )

                            base_method_docstring = ast.get_docstring(base_method)
                            if not base_method_docstring:
                                return False, (
                                    f"Method '{method_name}' docstring missing "
                                    f"in base class '{base_class_name}'. "
                                    f"Expected: {original_method_docstring[:50]}..."
                                )
                            if base_method_docstring.strip() != original_method_docstring.strip():
                                return False, (
                                    f"Method '{method_name}' docstring mismatch "
                                    f"in base class '{base_class_name}'. "
                                    f"Expected: {original_method_docstring[:50]}..., "
                                    f"Got: {base_method_docstring[:50]}..."
                                )

            return True, None

        except Exception as e:
            return False, f"Error during docstring validation: {str(e)}"


class ClassMerger:
    """
    Class for merging multiple classes into a single base class.

    This is the inverse operation of extract-superclass - it combines
    multiple classes into one base class.
    """

    def __init__(self, file_path: Path) -> None:
        """Initialize class merger."""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        self.backup_path: Optional[Path] = None
        self.original_content: str = ""
        self.tree: Optional[ast.Module] = None

    def create_backup(self) -> Path:
        """Create backup copy of the file."""
        backup_dir = self.file_path.parent / ".code_mapper_backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = int(Path(self.file_path).stat().st_mtime)
        backup_path = (
            backup_dir / f"{self.file_path.stem}_{timestamp}.py.backup"
        )
        shutil.copy2(self.file_path, backup_path)
        self.backup_path = backup_path
        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def restore_backup(self) -> None:
        """Restore file from backup."""
        if self.backup_path and self.backup_path.exists():
            shutil.copy2(self.backup_path, self.file_path)
            logger.info(f"File restored from backup: {self.backup_path}")

    def load_file(self) -> None:
        """Load and parse file content."""
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.original_content = f.read()
        self.tree = ast.parse(
            self.original_content, filename=str(self.file_path)
        )

    def find_class(self, class_name: str) -> Optional[ast.ClassDef]:
        """Find class definition in AST."""
        if not self.tree:
            return None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def extract_init_properties(self, class_node: ast.ClassDef) -> List[str]:
        """Extract properties initialized in __init__."""
        properties = []
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    # Handle regular assignments: self.attr = value
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    properties.append(target.attr)
                    # Handle annotated assignments: self.attr: Type = value
                    elif isinstance(stmt, ast.AnnAssign):
                        if isinstance(stmt.target, ast.Attribute):
                            if (
                                isinstance(stmt.target.value, ast.Name)
                                and stmt.target.value.id == "self"
                            ):
                                properties.append(stmt.target.attr)
        return properties

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate merge configuration."""
        errors = []

        base_class = config.get("base_class")
        if not base_class:
            errors.append("base_class not specified")

        source_classes = config.get("source_classes", [])
        if not source_classes:
            errors.append("source_classes list is empty")

        # Check that base_class doesn't already exist
        if self.find_class(base_class):
            errors.append(f"Base class '{base_class}' already exists")

        # Check that all source classes exist
        for src_class in source_classes:
            if not self.find_class(src_class):
                errors.append(f"Source class '{src_class}' not found")

        return len(errors) == 0, errors

    def merge_classes(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Merge multiple classes into a single base class.

        Args:
            config: Configuration dict with:
                - base_class: Name of the new merged class
                - source_classes: List of class names to merge
                - merge_methods: List of method names to merge (optional)
                - merge_props: List of property names to merge (optional)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Create backup
            self.create_backup()

            # Load file
            self.load_file()

            # Validate configuration
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                return False, f"Configuration validation failed: {'; '.join(errors)}"

            base_class_name = config.get("base_class")
            source_classes = config.get("source_classes", [])

            # Collect original members BEFORE operation
            all_original_props = set()
            all_original_methods = set()

            source_nodes = []
            for src_class_name in source_classes:
                src_node = self.find_class(src_class_name)
                if not src_node:
                    return False, f"Source class '{src_class_name}' not found"
                source_nodes.append(src_node)

                # Collect properties and methods
                props = set(self.extract_init_properties(src_node))
                all_original_props.update(props)

                for item in src_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_original_methods.add(item.name)

            # Perform merge
            new_content = self._perform_merge(config, source_nodes)

            # Write new content
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Validate Python syntax
            is_valid, error_msg = self.validate_python_syntax()
            if not is_valid:
                # Restore backup
                self.restore_backup()
                return False, f"Python validation failed: {error_msg}"

            # Validate completeness
            is_complete, completeness_error = self.validate_completeness(
                base_class_name, source_classes, all_original_props, all_original_methods
            )
            if not is_complete:
                # Restore backup
                self.restore_backup()
                return False, f"Completeness validation failed: {completeness_error}"

            # Validate that all docstrings are preserved
            is_docstrings_valid, docstrings_error = self.validate_docstrings(
                source_nodes, config
            )
            if not is_docstrings_valid:
                # Restore backup
                self.restore_backup()
                return False, f"Docstring validation failed: {docstrings_error}"

            # Import validation is optional
            try:
                import_valid, import_error = self.validate_imports()
                if not import_valid:
                    logger.warning(f"Import validation warning: {import_error}")
            except Exception as e:
                logger.warning(f"Import validation skipped: {e}")

            return True, "Class merge completed successfully"

        except Exception as e:
            # Restore backup on any error
            if self.backup_path:
                self.restore_backup()
            return False, f"Error during merge: {str(e)}"

    def _perform_merge(
        self, config: Dict[str, Any], source_nodes: List[ast.ClassDef]
    ) -> str:
        """Perform the actual class merging."""
        if not self.tree:
            raise ValueError("AST tree not loaded")

        base_class_name = config.get("base_class")
        merge_methods = config.get("merge_methods", [])
        merge_props = config.get("merge_props", [])

        # Build merged class
        merged_class_code = self._build_merged_class(
            base_class_name, source_nodes, merge_methods, merge_props
        )

        # Remove source classes
        lines = self.original_content.split("\n")
        updated_lines = lines.copy()

        # Find and remove source classes
        class_positions = {}
        for src_node in source_nodes:
            class_positions[src_node.name] = (
                src_node.lineno - 1,
                self._find_class_end(src_node, lines),
            )

        # Remove classes in reverse order to preserve line numbers
        for src_name in sorted(class_positions.keys(), reverse=True):
            start, end = class_positions[src_name]
            del updated_lines[start:end]

        # Insert merged class at position of first source class
        first_pos = min(pos[0] for pos in class_positions.values())
        updated_lines.insert(first_pos, merged_class_code)

        return "\n".join(updated_lines)

    def _build_merged_class(
        self,
        base_class_name: str,
        source_nodes: List[ast.ClassDef],
        merge_methods: List[str],
        merge_props: List[str],
    ) -> str:
        """Build the merged class code."""
        lines = []
        lines.append(f"class {base_class_name}:")
        lines.append('    """Merged class combining functionality from multiple classes."""')
        lines.append("")

        # Collect all properties
        all_props = set()
        for src_node in source_nodes:
            props = set(self.extract_init_properties(src_node))
            all_props.update(props)

        if all_props:
            lines.append("    def __init__(self):")
            for prop in sorted(all_props):
                lines.append(f"        self.{prop} = None")
            lines.append("")

        # Collect all methods
        all_methods = {}
        for src_node in source_nodes:
            for item in src_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name not in all_methods:
                        all_methods[item.name] = item

        # Add methods
        for method_name in sorted(all_methods.keys()):
            if merge_methods and method_name not in merge_methods:
                continue
            method_node = all_methods[method_name]
            method_code = self._extract_method_code(method_node, "    ")
            if method_code.strip():
                lines.append(method_code)
                lines.append("")

        return "\n".join(lines)

    def _extract_method_code(self, method_node: Any, indent: str) -> str:
        """Extract method code as string with proper indentation, including comments."""
        lines = self.original_content.split("\n")
        method_start_line = method_node.lineno - 1

        # Find method end - use end_lineno if available,
        # otherwise find by indentation
        if hasattr(method_node, "end_lineno") and method_node.end_lineno:
            method_end = method_node.end_lineno
        else:
            # Fallback: find next statement at same or less indentation
            method_indent = len(lines[method_start_line]) - len(lines[method_start_line].lstrip())
            method_end = method_start_line + 1
            for i in range(method_start_line + 1, len(lines)):
                line = lines[i]
                if line.strip() and not line.strip().startswith("#"):
                    line_indent = len(line) - len(line.lstrip())
                    if line_indent <= method_indent:
                        method_end = i
                        break
                method_end = i + 1

        # Find comments before method (on same or higher indentation level)
        method_indent = len(lines[method_start_line]) - len(lines[method_start_line].lstrip())
        actual_start = method_start_line
        
        # Look backwards for comments and empty lines
        for i in range(method_start_line - 1, -1, -1):
            line = lines[i]
            if not line.strip():
                # Empty line - continue looking
                continue
            elif line.strip().startswith("#"):
                # Comment line - check if it's at same or less indentation
                comment_indent = len(line) - len(line.lstrip())
                if comment_indent <= method_indent:
                    # This comment belongs to the method
                    actual_start = i
                else:
                    # Comment is more indented, might be part of previous method
                    break
            else:
                # Non-comment, non-empty line - stop here
                break

        method_lines = lines[actual_start:method_end]

        if method_lines:
            # Find first non-empty line for base indent
            original_indent = 0
            for line in method_lines:
                if line.strip():
                    original_indent = len(line) - len(line.lstrip())
                    break

            adjusted_lines = []
            for line in method_lines:
                if line.strip():
                    current_indent = len(line) - len(line.lstrip())
                    indent_diff = current_indent - original_indent
                    new_indent = indent + " " * indent_diff
                    adjusted_lines.append(new_indent + line.lstrip())
                else:
                    adjusted_lines.append("")

            result = "\n".join(adjusted_lines)
            if result.strip():
                return result
        return ""

    def _find_class_end(self, class_node: ast.ClassDef, lines: List[str]) -> int:
        """Find the end line of a class definition."""
        if class_node.body:
            last_stmt = class_node.body[-1]
            if hasattr(last_stmt, "end_lineno") and last_stmt.end_lineno:
                return last_stmt.end_lineno
            else:
                class_indent = len(lines[class_node.lineno - 1]) - len(
                    lines[class_node.lineno - 1].lstrip()
                )
                for i in range(last_stmt.lineno, len(lines)):
                    line = lines[i]
                    if line.strip() and not line.strip().startswith("#"):
                        indent = len(line) - len(line.lstrip())
                        if indent <= class_indent:
                            return i
                return len(lines)
        return class_node.lineno

    def validate_python_syntax(self) -> tuple[bool, Optional[str]]:
        """Validate Python syntax of modified file."""
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", str(self.file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, result.stderr
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Syntax validation timeout"
        except Exception as e:
            return False, str(e)

    def validate_imports(self) -> tuple[bool, Optional[str]]:
        """Try to import the modified module."""
        try:
            import sys

            sys.path.insert(0, str(self.file_path.parent))
            module_name = self.file_path.stem
            try:
                if module_name in sys.modules:
                    del sys.modules[module_name]
                __import__(module_name)
                return True, None
            except ImportError as e:
                return False, str(e)
            finally:
                sys.path.remove(str(self.file_path.parent))
                if module_name in sys.modules:
                    del sys.modules[module_name]

        except Exception as e:
            return False, str(e)

    def validate_completeness(
        self,
        base_class_name: str,
        source_classes: List[str],
        original_props: set,
        original_methods: set,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all original properties and methods are present.

        Uses pre-collected original_props and original_methods for strict
        validation against the merged class.
        """
        try:
            # Reload file to get new AST
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))

            # Find merged class
            merged_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                    merged_class = node
                    break

            if not merged_class:
                return False, f"Merged class '{base_class_name}' not found"

            # Collect properties and methods from merged class
            new_props = set(self.extract_init_properties(merged_class))
            new_methods = set()
            for item in merged_class.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    new_methods.add(item.name)

            # Validate properties - strict check
            missing_props = original_props - new_props
            if missing_props:
                return (
                    False,
                    f"Missing properties after merge: {missing_props}. "
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
                    f"Missing methods after merge: {missing_methods}. "
                    f"Original: {len(regular_original)}, Found: {len(regular_new)}",
                )

            return True, None

        except Exception as e:
            return False, f"Error during completeness validation: {str(e)}"

    def validate_docstrings(
        self,
        source_nodes: List[ast.ClassDef],
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that all docstrings are preserved in merged class.

        Args:
            source_nodes: Original source class AST nodes
            config: Merge configuration

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Reload file to get new AST
            with open(self.file_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            new_tree = ast.parse(new_content, filename=str(self.file_path))

            base_class_name = config.get("base_class")

            # Find merged class
            merged_class = None
            for node in ast.walk(new_tree):
                if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                    merged_class = node
                    break

            if not merged_class:
                return False, f"Merged class '{base_class_name}' not found after merge"

            # Collect all method docstrings from source classes
            source_method_docstrings = {}
            for src_node in source_nodes:
                for item in src_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_docstring = ast.get_docstring(item)
                        if method_docstring:
                            # If method appears in multiple classes, use first one
                            if item.name not in source_method_docstrings:
                                source_method_docstrings[item.name] = method_docstring

            # Check method docstrings in merged class
            for method_name, expected_docstring in source_method_docstrings.items():
                # Find method in merged class
                merged_method = None
                for item in merged_class.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        merged_method = item
                        break

                if not merged_method:
                    return False, (
                        f"Method '{method_name}' not found "
                        f"in merged class '{base_class_name}'"
                    )

                merged_method_docstring = ast.get_docstring(merged_method)
                if not merged_method_docstring:
                    return False, (
                        f"Method '{method_name}' docstring missing "
                        f"in merged class '{base_class_name}'. "
                        f"Expected: {expected_docstring[:50]}..."
                    )
                if merged_method_docstring.strip() != expected_docstring.strip():
                    return False, (
                        f"Method '{method_name}' docstring mismatch "
                        f"in merged class '{base_class_name}'. "
                        f"Expected: {expected_docstring[:50]}..., "
                        f"Got: {merged_method_docstring[:50]}..."
                    )

            return True, None

        except Exception as e:
            return False, f"Error during docstring validation: {str(e)}"
