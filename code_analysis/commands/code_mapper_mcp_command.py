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
    """Update code indexes by analyzing project files and adding them to database.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "update_indexes"
    version = "1.0.0"
    descr = "Update code indexes by analyzing project files and adding them to database"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # This can be long-running, use queue

    @classmethod
    def get_schema(cls: type["UpdateIndexesMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema for command parameters.
        """
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

    def _extract_docstring(
        self: "UpdateIndexesMCPCommand", node: ast.AST
    ) -> Optional[str]:
        """Extract docstring from an AST node.

        Args:
            self: Command instance.
            node: AST node to inspect.

        Returns:
            Docstring text if present; otherwise None.
        """
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
        ):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                return node.body[0].value.value
        return None

    def _extract_args(
        self: "UpdateIndexesMCPCommand", node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[str]:
        """Extract argument names from function node.

        Args:
            self: Command instance.
            node: Function node.

        Returns:
            List of argument names excluding 'self'.
        """
        args: list[str] = []
        for arg in node.args.args:
            if arg.arg != "self":
                args.append(arg.arg)
        return args

    def _analyze_file(
        self: "UpdateIndexesMCPCommand",
        database: Any,
        file_path: Path,
        project_id: str,
        root_path: Path,
    ) -> Dict[str, Any]:
        """Analyze a single Python file and add/update entries in the database.

        Args:
            self: Command instance.
            database: CodeDatabase instance.
            file_path: File to analyze.
            project_id: Project identifier.
            root_path: Root path to compute relative file paths.

        Returns:
            Per-file result dictionary with status and extracted counts.
        """
        try:
            file_path = file_path.resolve()
            root_path = root_path.resolve()

            try:
                rel_path = str(file_path.relative_to(root_path))
            except ValueError:
                logger.warning(
                    f"File {file_path} is outside root {root_path}, using absolute path"
                )
                rel_path = str(file_path)

            if not file_path.exists():
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": "File does not exist",
                    "error_type": "FileNotFoundError",
                }

            try:
                file_stat = file_path.stat()
                file_mtime = file_stat.st_mtime
            except OSError as e:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": f"Cannot stat file: {e}",
                    "error_type": type(e).__name__,
                }

            try:
                file_content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as e:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": f"Unicode decode error: {e}",
                    "error_type": "UnicodeDecodeError",
                }
            except Exception as e:
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": f"Cannot read file: {e}",
                    "error_type": type(e).__name__,
                }

            lines = len(file_content.splitlines())

            file_record = database.get_file_by_path(rel_path, project_id)
            if file_record:
                file_id = file_record["id"]
                if file_record.get("last_modified") != file_mtime:
                    try:
                        has_docstring = bool(
                            self._extract_docstring(ast.parse(file_content))
                        )
                    except SyntaxError:
                        has_docstring = False
                    database.add_file(
                        rel_path, lines, file_mtime, has_docstring, project_id
                    )
                    updated_record = database.get_file_by_path(rel_path, project_id)
                    if updated_record:
                        file_id = updated_record["id"]
            else:
                try:
                    has_docstring = bool(
                        self._extract_docstring(ast.parse(file_content))
                    )
                except SyntaxError:
                    has_docstring = False
                database.add_file(
                    rel_path, lines, file_mtime, has_docstring, project_id
                )
                file_record = database.get_file_by_path(rel_path, project_id)
                if not file_record:
                    return {
                        "file": rel_path,
                        "status": "error",
                        "error": "Failed to create file record",
                        "error_type": "DatabaseError",
                    }
                file_id = file_record["id"]

            try:
                tree = ast.parse(file_content, filename=str(file_path))
            except SyntaxError as e:
                logger.warning(f"Syntax error in {rel_path}: {e}")
                return {"file": rel_path, "status": "syntax_error", "error": str(e)}

            import hashlib

            ast_json = json.dumps(ast.dump(tree))
            ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        database.save_ast_tree(
                            file_id,
                            project_id,
                            ast_json,
                            ast_hash,
                            file_mtime,
                            overwrite=True,
                        )
                    )
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error saving AST for {rel_path}: {e}", exc_info=True)
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": f"Failed to save AST: {e}",
                    "error_type": type(e).__name__,
                }

            cst_hash = hashlib.sha256(file_content.encode()).hexdigest()
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        database.save_cst_tree(
                            file_id,
                            project_id,
                            file_content,
                            cst_hash,
                            file_mtime,
                            overwrite=True,
                        )
                    )
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error saving CST for {rel_path}: {e}", exc_info=True)
                return {
                    "file": rel_path,
                    "status": "error",
                    "error": f"Failed to save CST: {e}",
                    "error_type": type(e).__name__,
                }

            classes_added = 0
            functions_added = 0
            methods_added = 0
            imports_added = 0

            class_nodes: dict[ast.ClassDef, int] = {}

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    docstring = self._extract_docstring(node)
                    bases: list[str] = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            bases.append(base.id)
                        else:
                            try:
                                bases.append(ast.unparse(base))
                            except AttributeError:
                                bases.append(str(base))
                    class_id = database.add_class(
                        file_id, node.name, node.lineno, docstring, bases
                    )
                    classes_added += 1
                    class_nodes[node] = class_id

                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_docstring = self._extract_docstring(item)
                            method_args = self._extract_args(item)
                            database.add_method(
                                class_id,
                                item.name,
                                item.lineno,
                                method_args,
                                method_docstring,
                            )
                            methods_added += 1

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_method = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            if any(
                                node == item
                                for item in parent.body
                                if isinstance(
                                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                                )
                            ):
                                is_method = True
                                break

                    if not is_method:
                        docstring = self._extract_docstring(node)
                        args = self._extract_args(node)
                        database.add_function(
                            file_id, node.name, node.lineno, args, docstring
                        )
                        functions_added += 1

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
            error_msg = f"Error analyzing {file_path}: {e}"
            logger.error(error_msg, exc_info=True)
            import sys
            import traceback

            print(f"ERROR: {error_msg}", file=sys.stderr, flush=True)
            print(f"ERROR_TYPE: {type(e).__name__}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            return {
                "file": str(file_path),
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def execute(
        self: "UpdateIndexesMCPCommand",
        root_dir: str,
        max_lines: int = 400,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute code index update.

        Args:
            self: Command instance.
            root_dir: Root directory to analyze.
            max_lines: Maximum lines per file threshold (for reporting).
            **kwargs: Extra parameters (may include 'context' with ProgressTracker).

        Returns:
            SuccessResult with update results or ErrorResult on failure.
        """
        from ..core.db_integrity import (
            backup_sqlite_files,
            check_sqlite_integrity,
            recreate_sqlite_database_file,
        )
        from ..core.progress_tracker import get_progress_tracker_from_context
        from ..core.worker_launcher import (
            default_faiss_index_path,
            start_file_watcher_worker,
            start_vectorization_worker,
            stop_worker_type,
        )

        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )

        try:
            root_path = self._validate_root_dir(root_dir)

            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description("Scanning for Python files...")
                progress_tracker.set_progress(0)

            data_dir = root_path / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "code_analysis.db"

            db_check = check_sqlite_integrity(db_path)
            db_repaired = False
            db_backup_paths: list[str] = []
            if not db_check.ok:
                if progress_tracker:
                    progress_tracker.set_description(
                        f"Database corrupted ({db_check.message}); backing up and recreating..."
                    )

                stop_worker_type("file_watcher", timeout=5.0)
                stop_worker_type("vectorization", timeout=5.0)

                db_backup_paths = list(
                    backup_sqlite_files(db_path, backup_dir=data_dir)
                )
                recreate_sqlite_database_file(db_path)
                db_repaired = True

            database = self._open_database(root_dir, auto_analyze=False)
            try:
                project_id = self._get_project_id(database, root_path, None)
                if not project_id:
                    project_id = database.get_or_create_project(
                        str(root_path), name=root_path.name
                    )

                python_files: list[Path] = []
                for walk_root, dirs, files in os.walk(root_path):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".")
                        and d
                        not in ["__pycache__", "node_modules", ".git", "data", "logs"]
                    ]
                    for file in files:
                        if file.endswith(".py"):
                            python_files.append(Path(walk_root) / file)

                files_total = len(python_files)
                if progress_tracker:
                    progress_tracker.set_description(
                        f"Processing {files_total} Python file(s) for indexing..."
                    )
                    progress_tracker.set_progress(0)

                if files_total == 0:
                    if progress_tracker:
                        progress_tracker.set_progress(100)
                        progress_tracker.set_description(
                            "No Python files found; nothing to index"
                        )
                        progress_tracker.set_status("completed")
                    return SuccessResult(
                        data={
                            "root_dir": str(root_path),
                            "project_id": project_id,
                            "files_processed": 0,
                            "files_total": 0,
                            "files_discovered": 0,
                            "errors": 0,
                            "syntax_errors": 0,
                            "classes": 0,
                            "functions": 0,
                            "methods": 0,
                            "imports": 0,
                            "db_repaired": db_repaired,
                            "db_backup_paths": db_backup_paths,
                            "message": "No Python files found",
                        }
                    )

                def process_files() -> list[Dict[str, Any]]:
                    """Process files and update progress.

                    Returns:
                        List of per-file results.
                    """
                    results: list[Dict[str, Any]] = []
                    error_samples: list[Dict[str, str]] = []
                    last_percent = -1

                    for idx, file_path in enumerate(python_files):
                        result = self._analyze_file(
                            database, file_path, project_id, root_path
                        )
                        results.append(result)

                        if result.get("status") == "error" and len(error_samples) < 5:
                            error_samples.append(
                                {
                                    "file": result.get("file", str(file_path)),
                                    "error": result.get("error", "Unknown error"),
                                    "error_type": result.get("error_type", "Unknown"),
                                }
                            )

                        if progress_tracker:
                            percent = int(((idx + 1) / files_total) * 100)
                            if percent != last_percent:
                                progress_tracker.set_progress(percent)
                                progress_tracker.set_description(
                                    f"Indexing: {idx + 1}/{files_total} ({percent}%)"
                                )
                                last_percent = percent

                        if (idx + 1) % 100 == 0:
                            logger.info(f"Processed {idx + 1}/{files_total} files...")

                    if error_samples:
                        logger.warning(f"Sample errors (first {len(error_samples)}):")
                        for sample in error_samples:
                            logger.warning(
                                f"  {sample['file']}: {sample['error_type']} - {sample['error']}"
                            )

                    return results

                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(None, process_files)

                total = len(results)
                successful = sum(1 for r in results if r.get("status") == "success")
                errors = sum(1 for r in results if r.get("status") == "error")
                syntax_errors = sum(
                    1 for r in results if r.get("status") == "syntax_error"
                )
                total_classes = sum(r.get("classes", 0) for r in results)
                total_functions = sum(r.get("functions", 0) for r in results)
                total_methods = sum(r.get("methods", 0) for r in results)
                total_imports = sum(r.get("imports", 0) for r in results)

                worker_start: dict[str, Any] = {}
                if db_repaired:
                    try:
                        worker_start["file_watcher"] = start_file_watcher_worker(
                            db_path=str(db_path),
                            project_id=project_id,
                            watch_dirs=[str(root_path)],
                            scan_interval=60,
                            version_dir=str(
                                (root_path / "data" / "versions").resolve()
                            ),
                            worker_log_path=str(
                                (root_path / "logs" / "file_watcher.log").resolve()
                            ),
                            project_root=str(root_path),
                            ignore_patterns=[".git", "__pycache__", "data", "logs"],
                        ).__dict__
                    except Exception as e:
                        worker_start["file_watcher"] = {
                            "success": False,
                            "error": str(e),
                        }

                    try:
                        worker_start["vectorization"] = start_vectorization_worker(
                            db_path=str(db_path),
                            project_id=project_id,
                            faiss_index_path=default_faiss_index_path(str(root_path)),
                            vector_dim=384,
                            svo_config=None,
                            batch_size=10,
                            poll_interval=30,
                            worker_log_path=str(
                                (
                                    root_path / "logs" / "vectorization_worker.log"
                                ).resolve()
                            ),
                        ).__dict__
                    except Exception as e:
                        worker_start["vectorization"] = {
                            "success": False,
                            "error": str(e),
                        }

                if progress_tracker:
                    progress_tracker.set_progress(100)
                    progress_tracker.set_description("Indexing completed")
                    progress_tracker.set_status("completed")

                return SuccessResult(
                    data={
                        "root_dir": str(root_path),
                        "project_id": project_id,
                        "files_processed": successful,
                        "files_total": total,
                        "files_discovered": files_total,
                        "errors": errors,
                        "syntax_errors": syntax_errors,
                        "classes": total_classes,
                        "functions": total_functions,
                        "methods": total_methods,
                        "imports": total_imports,
                        "db_repaired": db_repaired,
                        "db_backup_paths": db_backup_paths,
                        "workers_restarted": worker_start,
                        "message": (
                            f"Indexes updated: {successful}/{total} files processed, "
                            f"{errors} errors, {syntax_errors} syntax errors"
                        ),
                    }
                )
            finally:
                database.close()

        except Exception as e:
            if progress_tracker:
                progress_tracker.set_status("failed")
            return self._handle_error(e, "INDEX_UPDATE_ERROR", "update_indexes")
