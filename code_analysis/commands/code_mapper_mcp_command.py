"""
MCP command wrapper for code index update.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import ast
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class UpdateIndexesMCPCommand(BaseMCPCommand):
    """Update code indexes by analyzing project files and adding them to database."""

    name = "update_indexes"
    version = "1.0.0"
    descr = "Update code indexes by analyzing project files and adding them to database"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # This can be long-running, use queue

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory to analyze",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines per file threshold",
                    "default": 400,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    def _extract_docstring(self, node: ast.AST) -> Optional[str]:
        """Extract docstring from AST node."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                return node.body[0].value.value
        return None

    def _extract_args(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """Extract argument names from function node."""
        args = []
        for arg in node.args.args:
            if arg.arg != "self":
                args.append(arg.arg)
        return args

    def _analyze_file(
        self, database: Any, file_path: Path, project_id: str, root_path: Path
    ) -> Dict[str, Any]:
        """Analyze a single Python file and add to database."""
        try:
            rel_path = str(file_path.relative_to(root_path))
            file_stat = file_path.stat()
            file_mtime = file_stat.st_mtime
            file_content = file_path.read_text(encoding="utf-8")
            lines = len(file_content.splitlines())

            # Check if file already exists
            file_record = database.get_file_by_path(rel_path, project_id)
            if file_record:
                file_id = file_record["id"]
                # Update file if modified
                if file_record.get("last_modified") != file_mtime:
                    database.add_file(
                        rel_path, lines, file_mtime, bool(self._extract_docstring(ast.parse(file_content))), project_id
                    )
            else:
                # Add new file
                has_docstring = bool(self._extract_docstring(ast.parse(file_content)))
                file_id = database.add_file(
                    rel_path, lines, file_mtime, has_docstring, project_id
                )

            # Parse AST
            try:
                tree = ast.parse(file_content, filename=str(file_path))
            except SyntaxError as e:
                logger.warning(f"Syntax error in {rel_path}: {e}")
                return {"file": rel_path, "status": "syntax_error", "error": str(e)}

            # Save AST (synchronously using existing connection)
            ast_json = json.dumps(ast.dump(tree))
            import hashlib
            ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
            # Use synchronous save - create a wrapper if needed
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(database.save_ast_tree(file_id, project_id, ast_json, ast_hash, file_mtime, overwrite=True))

            # Save CST (source code) for file restoration
            cst_hash = hashlib.sha256(file_content.encode()).hexdigest()
            loop.run_until_complete(database.save_cst_tree(file_id, project_id, file_content, cst_hash, file_mtime, overwrite=True))

            # Extract and save classes, functions, methods, imports
            classes_added = 0
            functions_added = 0
            methods_added = 0
            imports_added = 0

            # Track class contexts to identify methods vs functions
            class_nodes = {}
            
            # First pass: extract classes and their methods
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    docstring = self._extract_docstring(node)
                    bases = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            bases.append(base.id)
                        else:
                            try:
                                bases.append(ast.unparse(base))
                            except AttributeError:
                                # Python < 3.9 doesn't have ast.unparse
                                bases.append(str(base))
                    class_id = database.add_class(file_id, node.name, node.lineno, docstring, bases)
                    classes_added += 1
                    class_nodes[node] = class_id

                    # Extract methods
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_docstring = self._extract_docstring(item)
                            method_args = self._extract_args(item)
                            database.add_method(
                                class_id, item.name, item.lineno, method_args, method_docstring
                            )
                            methods_added += 1

            # Second pass: extract top-level functions (not in classes)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Check if this function is inside a class
                    is_method = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            if any(node == item for item in parent.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))):
                                is_method = True
                                break
                    
                    if not is_method:
                        docstring = self._extract_docstring(node)
                        args = self._extract_args(node)
                        database.add_function(file_id, node.name, node.lineno, args, docstring)
                        functions_added += 1

            # Third pass: extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        database.add_import(
                            file_id, alias.name, None, "import", node.lineno
                        )
                        imports_added += 1
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        database.add_import(
                            file_id, alias.name, module, "import_from", node.lineno
                        )
                        imports_added += 1

            # Mark file for chunking
            database.mark_file_needs_chunking(rel_path, project_id)

            return {
                "file": rel_path,
                "status": "success",
                "classes": classes_added,
                "functions": functions_added,
                "methods": methods_added,
                "imports": imports_added,
            }

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}", exc_info=True)
            return {"file": str(file_path), "status": "error", "error": str(e), "error_type": type(e).__name__}

    async def execute(
        self,
        root_dir: str,
        max_lines: int = 400,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute code index update.

        Args:
            root_dir: Root directory to analyze
            max_lines: Maximum lines per file threshold (for reporting)

        Returns:
            SuccessResult with update results or ErrorResult on failure
        """
        try:
            root_path = self._validate_root_dir(root_dir)

            # Open database and get/create project
            database = self._open_database(root_dir, auto_analyze=False)
            try:
                project_id = self._get_project_id(database, root_path, None)
                if not project_id:
                    project_id = database.get_or_create_project(
                        str(root_path), name=root_path.name
                    )

                # Find all Python files
                python_files = []
                for root, dirs, files in os.walk(root_path):
                    # Skip hidden directories and common ignore patterns
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".")
                        and d not in ["__pycache__", "node_modules", ".git", "data", "logs"]
                    ]
                    for file in files:
                        if file.endswith(".py"):
                            file_path = Path(root) / file
                            python_files.append(file_path)

                # Process files
                def process_files():
                    results = []
                    for file_path in python_files:
                        result = self._analyze_file(database, file_path, project_id, root_path)
                        results.append(result)
                    return results

                # Run in executor to avoid blocking
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(None, process_files)

                # Count statistics
                total = len(results)
                successful = sum(1 for r in results if r.get("status") == "success")
                errors = sum(1 for r in results if r.get("status") == "error")
                syntax_errors = sum(1 for r in results if r.get("status") == "syntax_error")
                total_classes = sum(r.get("classes", 0) for r in results)
                total_functions = sum(r.get("functions", 0) for r in results)
                total_methods = sum(r.get("methods", 0) for r in results)
                total_imports = sum(r.get("imports", 0) for r in results)

                return SuccessResult(
                    data={
                        "root_dir": str(root_path),
                        "project_id": project_id,
                        "files_processed": successful,
                        "files_total": total,
                        "errors": errors,
                        "syntax_errors": syntax_errors,
                        "classes": total_classes,
                        "functions": total_functions,
                        "methods": total_methods,
                        "imports": total_imports,
                        "message": f"Indexes updated: {successful}/{total} files processed, {errors} errors, {syntax_errors} syntax errors",
                    }
                )
            finally:
                database.close()

        except Exception as e:
            return self._handle_error(e, "INDEX_UPDATE_ERROR", "update_indexes")
