"""
Module package_splitter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

from .base import BaseRefactorer
from .formatters import format_code_with_black

logger = logging.getLogger(__name__)


class FileToPackageSplitter(BaseRefactorer):
    """
    Class for splitting a single file into a package with multiple modules.

    This class splits a large file into a package structure:
    - Creates a package directory
    - Splits classes/functions into separate modules
    - Creates __init__.py with proper imports
    - Preserves all dependencies and imports
    """

    def __init__(self, file_path: Path) -> None:
        """
        Initialize file to package splitter.

        Args:
            file_path: Path to the file to split
        """
        super().__init__(file_path)
        self.package_path: Optional[Path] = None

    def split_file_to_package(
        self, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Split file into package structure.

        Args:
            config: Configuration dict with:
                - package_name: Name of the package directory
                - modules: Dict mapping module_name to list of class/function names
                - shared_imports: List of imports to keep in all modules
                - package_imports: List of imports for __init__.py

        Returns:
            Tuple of (success, error_message)
        """
        try:
            self.create_backup()
            self.load_file()
            is_valid, error_msg = self._validate_package_config(config)
            if not is_valid:
                return (False, error_msg)
            package_name = config.get("package_name")
            if not package_name:
                return (False, "package_name not specified in config")
            self.package_path = self.file_path.parent / package_name
            if self.package_path.exists():
                return (False, f"Package directory already exists: {self.package_path}")
            self.package_path.mkdir(exist_ok=True)
            original_imports = self._extract_imports()
            modules_config = config.get("modules", {})
            created_modules = []
            for module_name, entities in modules_config.items():
                module_path = self.package_path / f"{module_name}.py"
                module_content = self._build_module(
                    module_name, entities, original_imports, config
                )
                with open(module_path, "w", encoding="utf-8") as f:
                    f.write(module_content)
                created_modules.append(module_name)
            main_class_name = None
            main_class_node: Optional[ast.ClassDef] = None
            for node in self.tree.body:
                if isinstance(node, ast.ClassDef):
                    main_class_name = node.name
                    main_class_node = node
                    break
            bind_method_names: set[str] = set()
            if main_class_node is not None:
                for item in main_class_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        bind_method_names.add(item.name)

            extra_exports: set[str] = set()
            if bind_method_names and modules_config:
                for module_name, entities in modules_config.items():
                    if module_name == "base":
                        continue
                    for name in entities:
                        if name == "__init__":
                            continue
                        if name in bind_method_names:
                            continue
                        if main_class_name and name == main_class_name:
                            continue
                        extra_exports.add(name)

            init_content = self._build_init_file(
                created_modules,
                config.get("package_imports", []),
                main_class_name=main_class_name,
                modules_config=modules_config,
                bind_names=bind_method_names,
                extra_exports=sorted(extra_exports),
            )
            init_path = self.package_path / "__init__.py"
            with open(init_path, "w", encoding="utf-8") as f:
                f.write(init_content)
            for module_file in self.package_path.glob("*.py"):
                format_code_with_black(module_file)
            for module_file in self.package_path.glob("*.py"):
                is_valid, error_msg = self._validate_file_syntax(module_file)
                if not is_valid:
                    self.restore_backup()
                    return (False, f"Syntax error in {module_file.name}: {error_msg}")
            backup_name = self.file_path.stem + "_original.py.backup"
            backup_file = self.package_path.parent / backup_name
            shutil.copy2(self.file_path, backup_file)

            shim_content = self._build_shim_file(
                package_name=package_name,
                main_class_name=main_class_name,
                exports=sorted(extra_exports),
            )
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(shim_content)
            format_code_with_black(self.file_path)
            logger.info(f"File split into package: {self.package_path}")
            return (True, f"File successfully split into package: {self.package_path}")
        except Exception as e:
            logger.exception("Error splitting file to package: %s", e)
            if self.package_path and self.package_path.exists():
                shutil.rmtree(self.package_path)
            return (False, f"Error splitting file to package: {str(e)}")

    def _validate_package_config(
        self, config: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate package split configuration."""
        if not config.get("package_name"):
            return (False, "package_name not specified")
        modules = config.get("modules", {})
        if not modules:
            return (False, "modules configuration is empty")
        all_entities = set()
        for module_entities in modules.values():
            all_entities.update(module_entities)
        if not self.tree:
            return (False, "File not loaded")

        # Find main class (CodeDatabase or first class)
        main_class = None
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef):
                main_class = node
                break

        file_entities = set()
        if main_class:
            # Extract methods from class
            for item in main_class.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    file_entities.add(item.name)
        else:
            # Fallback: extract top-level functions and classes
            for node in ast.walk(self.tree):
                if isinstance(node, ast.ClassDef):
                    file_entities.add(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name not in ("__init__", "__new__", "__del__"):
                        file_entities.add(node.name)

        missing_entities = all_entities - file_entities
        if missing_entities:
            return (False, f"Entities not found in file: {missing_entities}")
        return (True, None)

    def _extract_imports(self) -> List[ast.stmt]:
        """Extract all import statements from the file."""
        imports = []
        if not self.tree:
            return imports
        for node in self.tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
        return imports

    def _build_module(
        self,
        module_name: str,
        entities: List[str],
        original_imports: List[ast.stmt],
        config: Dict[str, Any],
    ) -> str:
        """Build content for a module file."""
        lines = []
        lines.append('"""')
        lines.append(f"Module {module_name}.")
        lines.append("")
        lines.append("Author: Vasiliy Zdanovskiy")
        lines.append("email: vasilyvz@gmail.com")
        lines.append('"""')
        lines.append("")
        shared_imports = config.get("shared_imports", [])
        for imp in shared_imports:
            lines.append(imp)
        for imp_node in original_imports:
            imp_str = ast.unparse(imp_node)
            lines.append(imp_str)
        lines.append("")
        if not self.tree:
            return "\n".join(lines)

        # First, find the main class (CodeDatabase)
        main_class = None
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef):
                main_class = node
                break

        if main_class:
            # Build class with only selected methods
            class_lines = []

            # Only add class definition in base module
            if module_name == "base":
                class_lines.append(f"class {main_class.name}:")
                docstring = ast.get_docstring(main_class)
                if docstring:
                    class_lines.append(f'    """{docstring}"""')
                else:
                    class_lines.append(f'    """{main_class.name} class."""')
                class_lines.append("")

            # Add __init__ only in base module
            if module_name == "base" and "__init__" in entities:
                for item in main_class.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == "__init__"
                    ):
                        init_code = self._extract_method_code(item, "    ")
                        class_lines.append(init_code)
                        break

            # Add other methods
            if module_name == "base":
                # In base module, methods are inside the class
                for item in main_class.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name in entities and item.name != "__init__":
                            method_code = self._extract_method_code(item, "    ")
                            class_lines.append(method_code)
                if class_lines:
                    lines.append("\n".join(class_lines))
            else:
                # In other modules, methods are defined as module-level functions
                # They will be added to the class in __init__.py
                for item in main_class.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name in entities:
                            # Extract as function - convert method to function
                            # Use _extract_method_code but then remove class-level indentation
                            method_code = self._extract_method_code(item, "    ")
                            method_lines = method_code.split("\n")
                            # Remove first 4 spaces from each line (class-level indentation)
                            adjusted_lines = []
                            for line in method_lines:
                                if line.startswith("    "):
                                    adjusted_lines.append(line[4:])  # Remove 4 spaces
                                elif line.strip() == "":
                                    adjusted_lines.append("")  # Keep empty lines
                                else:
                                    # Line doesn't start with 4 spaces - might be continuation
                                    # Keep as is but ensure it's not indented too much
                                    adjusted_lines.append(
                                        line.lstrip() if not line.strip() else line
                                    )
                            method_code = "\n".join(adjusted_lines)
                            lines.append(method_code)
                            lines.append("")  # Add blank line between methods
        else:
            # Fallback to original logic for top-level functions
            for node in self.tree.body:
                if isinstance(node, ast.ClassDef) and node.name in entities:
                    class_code = ast.unparse(node)
                    lines.append(class_code)
                    lines.append("")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in entities:
                        func_code = ast.unparse(node)
                        lines.append(func_code)
                        lines.append("")
        return "\n".join(lines)

    def _build_init_file(
        self,
        module_names: List[str],
        package_imports: List[str],
        main_class_name: Optional[str] = None,
        modules_config: Optional[Dict[str, List[str]]] = None,
        bind_names: Optional[set[str]] = None,
        extra_exports: Optional[List[str]] = None,
    ) -> str:
        """Build __init__.py content."""
        lines = []
        lines.append('"""')
        lines.append("Package initialization.")
        lines.append("")
        lines.append("Author: Vasiliy Zdanovskiy")
        lines.append("email: vasilyvz@gmail.com")
        lines.append('"""')
        lines.append("")
        for imp in package_imports:
            lines.append(imp)
        if package_imports:
            lines.append("")
        if main_class_name and modules_config and ("base" in module_names):
            lines.append(f"from .base import {main_class_name}")
            lines.append("")
            export_names: list[str] = [main_class_name]
            if extra_exports:
                export_names.extend(extra_exports)

            for module_name in module_names:
                if module_name == "base":
                    continue
                entities = modules_config.get(module_name, [])
                entities = [e for e in entities if e != "__init__"]
                if not entities:
                    continue
                lines.append(f"from .{module_name} import {', '.join(entities)}")
                for name in entities:
                    if bind_names and name in bind_names:
                        lines.append(f"{main_class_name}.{name} = {name}")
                    else:
                        export_names.append(name)
                lines.append("")
            unique_exports = sorted(set(export_names), key=str)
            lines.append(f"__all__ = {unique_exports!r}")
        else:
            for module_name in module_names:
                lines.append(f"from .{module_name} import *")
        return "\n".join(lines)

    def _build_shim_file(
        self,
        package_name: str,
        main_class_name: Optional[str],
        exports: Optional[List[str]] = None,
    ) -> str:
        """Build a small shim module to preserve backward-compatible imports."""
        cls = main_class_name or "MainClass"
        lines: list[str] = []
        lines.append('"""')
        lines.append("Legacy shim module.")
        lines.append("")
        lines.append("Author: Vasiliy Zdanovskiy")
        lines.append("email: vasilyvz@gmail.com")
        lines.append('"""')
        lines.append("")
        export_list: list[str] = [cls]
        if exports:
            export_list.extend(exports)
        unique_exports = sorted(set(export_list), key=str)
        lines.append(
            f"from .{package_name} import {', '.join(unique_exports)}  # noqa: F401"
        )
        lines.append("")
        lines.append(f"__all__ = {unique_exports!r}")
        return "\n".join(lines) + "\n"

    def _validate_file_syntax(self, file_path: Path) -> tuple[bool, Optional[str]]:
        """Validate Python syntax of a file."""
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", str(file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return (False, result.stderr)
            return (True, None)
        except subprocess.TimeoutExpired:
            return (False, "Syntax validation timeout")
        except Exception as e:
            return (False, str(e))
