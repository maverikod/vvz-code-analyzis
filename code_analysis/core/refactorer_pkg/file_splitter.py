"""
File to package splitter implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from typing import Any, Dict, Tuple

from .base import BaseRefactorer

logger = logging.getLogger(__name__)


class FileToPackageSplitter(BaseRefactorer):
    """Split a file into a package with multiple modules."""

    def split_file_to_package(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Split file into package according to configuration.

        Args:
            config: Split configuration with modules mapping
                Expected format:
                {
                    "modules": {
                        "module1": {
                            "classes": ["Class1", "Class2"],
                            "functions": ["func1", "func2"]
                        },
                        "module2": {
                            "classes": ["Class3"],
                            "functions": ["func3"]
                        }
                    }
                }

        Returns:
            Tuple of (success, message)
        """
        try:
            if not self.tree:
                return False, "Failed to parse file AST"

            modules = config.get("modules", {})
            if not modules:
                return False, "No modules specified in config"

            # Get file directory and name
            file_dir = self.file_path.parent
            file_stem = self.file_path.stem
            package_dir = file_dir / file_stem

            # Create package directory
            package_dir.mkdir(exist_ok=True)
            init_file = package_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text(
                    '"""Package created by split_file_to_package."""\n'
                )

            # Split code into modules
            source = self.original_content if hasattr(self, 'original_content') else self.file_path.read_text(encoding="utf-8")
            source_lines = source.splitlines(keepends=True)
            created_modules = []

            for module_name, module_config in modules.items():
                module_path = package_dir / f"{module_name}.py"
                module_content = self._build_module_content(
                    module_name, module_config, source_lines
                )
                module_path.write_text(module_content)
                created_modules.append(module_name)
                
                # Update database for new file
                if self.database and self.project_id and self.root_dir:
                    try:
                        # First, add file to database if it doesn't exist
                        import os
                        file_mtime = os.path.getmtime(module_path)
                        lines = len(module_content.splitlines())
                        has_docstring = module_content.strip().startswith('"""') or module_content.strip().startswith("'''")
                        
                        # Get or create dataset
                        dataset_id = self.database.get_or_create_dataset(
                            project_id=self.project_id,
                            root_path=str(self.root_dir),
                            name=self.root_dir.name,
                        )
                        
                        # Add file to database (or update if exists)
                        module_file_id = self.database.add_file(
                            path=str(module_path),
                            lines=lines,
                            last_modified=file_mtime,
                            has_docstring=has_docstring,
                            project_id=self.project_id,
                            dataset_id=dataset_id,
                        )
                        
                        # Now update file data (this will parse AST/CST and extract entities)
                        try:
                            rel_path = str(module_path.relative_to(self.root_dir))
                        except ValueError:
                            rel_path = str(module_path)
                        
                        update_result = self.database.update_file_data(
                            file_path=rel_path,
                            project_id=self.project_id,
                            root_dir=self.root_dir,
                        )
                        if not update_result.get("success"):
                            logger.warning(
                                f"Failed to update database for {module_path}: "
                                f"{update_result.get('error')}"
                            )
                        else:
                            logger.debug(
                                f"Database updated for {module_path}: "
                                f"AST={update_result.get('ast_updated')}, "
                                f"CST={update_result.get('cst_updated')}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error updating database for {module_path}: {e}",
                            exc_info=True,
                        )

            return (
                True,
                f"File split into package at {package_dir} with modules: {', '.join(created_modules)}",
            )
        except Exception as e:
            error_msg = f"Error splitting file to package: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def _build_module_content(
        self, module_name: str, module_config: Dict[str, Any], source_lines: list
    ) -> str:
        """
        Build content for a module.

        Args:
            module_name: Name of the module
            module_config: Configuration for this module
            source_lines: Original source lines

        Returns:
            Module content as string
        """
        # Get file docstring if exists
        file_docstring = self._get_file_docstring()

        # Collect classes and functions to include
        classes = module_config.get("classes", [])
        functions = module_config.get("functions", [])

        # Build imports (simplified - would need proper import analysis)
        imports = self._extract_imports()

        # Build module content
        lines = []
        if file_docstring:
            lines.append(f'"""{file_docstring}"""\n')
        else:
            lines.append(f'"""Module {module_name}."""\n')
        lines.append("\n")

        # Add imports
        if imports:
            lines.extend(imports)
            lines.append("\n")

        # Extract and add classes
        for class_name in classes:
            class_code = self._extract_class_code(class_name, source_lines)
            if class_code:
                lines.extend(class_code)
                lines.append("\n")

        # Extract and add functions
        for func_name in functions:
            func_code = self._extract_function_code(func_name, source_lines)
            if func_code:
                lines.extend(func_code)
                lines.append("\n")

        return "".join(lines)

    def _get_file_docstring(self) -> str:
        """Extract file-level docstring."""
        if not self.tree or not isinstance(self.tree.body[0], ast.Expr):
            return ""
        if isinstance(self.tree.body[0].value, ast.Constant):
            return self.tree.body[0].value.value
        return ""

    def _extract_imports(self) -> list:
        """Extract import statements from AST."""
        imports = []
        if not self.tree:
            return imports

        for node in self.tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Use source lines to preserve formatting
                start_line = node.lineno - 1
                end_line = (
                    node.end_lineno if hasattr(node, "end_lineno") else node.lineno
                )
                import_lines = self.source.splitlines(keepends=True)[
                    start_line:end_line
                ]
                imports.extend(import_lines)

        return imports

    def _extract_class_code(self, class_name: str, source_lines: list) -> list:
        """Extract class code from source lines."""
        class_node = self._find_class_in_ast(class_name)
        if not class_node:
            return []

        start_line = class_node.lineno - 1
        end_line = (
            class_node.end_lineno
            if hasattr(class_node, "end_lineno")
            else start_line + 1
        )

        # Find the actual end by looking for next top-level definition
        for i in range(end_line, len(source_lines)):
            line = source_lines[i].strip()
            if line and not line.startswith("#") and not line.startswith('"""'):
                # Check if this is a new top-level definition
                if line.startswith("class ") or line.startswith("def "):
                    end_line = i
                    break

        return source_lines[start_line:end_line]

    def _extract_function_code(self, func_name: str, source_lines: list) -> list:
        """Extract function code from source lines."""
        func_node = self._find_function_in_ast(func_name)
        if not func_node:
            return []

        start_line = func_node.lineno - 1
        end_line = (
            func_node.end_lineno if hasattr(func_node, "end_lineno") else start_line + 1
        )

        # Find the actual end
        for i in range(end_line, len(source_lines)):
            line = source_lines[i].strip()
            if line and not line.startswith("#") and not line.startswith('"""'):
                if line.startswith("class ") or line.startswith("def "):
                    end_line = i
                    break

        return source_lines[start_line:end_line]

    def _find_class_in_ast(self, class_name: str) -> ast.ClassDef:
        """Find class definition in AST."""
        if not self.tree:
            return None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def _find_function_in_ast(self, func_name: str) -> ast.FunctionDef:
        """Find function definition in AST."""
        if not self.tree:
            return None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return node
        return None
