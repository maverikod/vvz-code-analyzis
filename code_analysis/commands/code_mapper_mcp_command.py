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

from ..core.complexity_analyzer import calculate_complexity
from ..core.constants import (
    DATA_DIR_NAME,
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_MAX_FILE_LINES,
    LOGS_DIR_NAME,
)
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

        Notes:
            This schema is used by MCP Proxy for request validation and tool routing.

        Args:
            cls: Command class.

        Returns:
            JSON schema for command parameters.
        """
        return {
            "type": "object",
            "description": (
                "Analyze Python project by project_id and update code indexes in SQLite. "
                "Long-running; executed via queue. project_id is required (from create_project or list_projects)."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines per file threshold.",
                    "default": 400,
                    "examples": [400],
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "max_lines": 400,
                },
                {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
            ],
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
        force: bool = False,
    ) -> Dict[str, Any]:
        """Analyze a single Python file and add/update entries in the database.

        Args:
            self: Command instance.
            database: DatabaseClient instance.
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

            # Use absolute path for add_file to avoid path resolution issues
            # add_file normalizes paths internally, but we need to pass absolute path
            # to ensure it matches existing records
            abs_file_path = str(file_path.resolve())

            file_record = database.get_file_by_path(abs_file_path, project_id)
            if file_record:
                file_id = file_record["id"]
                # Update file record if last_modified differs or if force=True
                # This ensures file metadata is up to date
                last_modified = file_record.get("last_modified", 0)
                # Use epsilon comparison for float values
                epsilon = 0.01  # 10ms tolerance
                if force or abs(last_modified - file_mtime) > epsilon:
                    try:
                        has_docstring = bool(
                            self._extract_docstring(ast.parse(file_content))
                        )
                    except SyntaxError:
                        has_docstring = False
                    # Use absolute path to ensure correct file matching
                    updated_file_id = database.add_file(
                        abs_file_path,
                        lines,
                        file_mtime,
                        has_docstring,
                        project_id,
                    )
                    # add_file returns the file_id (may be same or different)
                    file_id = updated_file_id
                # Note: Even if last_modified matches and force=False, we still save AST/CST below
                # This is necessary for normal updates
            else:
                try:
                    has_docstring = bool(
                        self._extract_docstring(ast.parse(file_content))
                    )
                except SyntaxError:
                    has_docstring = False
                # Use absolute path to ensure correct file creation
                # add_file returns file_id directly, use it
                file_id = database.add_file(
                    abs_file_path,
                    lines,
                    file_mtime,
                    has_docstring,
                    project_id,
                )
                # Verify file_id is valid
                if not file_id:
                    return {
                        "file": rel_path,
                        "status": "error",
                        "error": "Failed to create file record",
                        "error_type": "DatabaseError",
                    }

            try:
                # Use parse_with_comments to preserve comments in AST
                from ..core.ast_utils import parse_with_comments

                tree = parse_with_comments(file_content, filename=str(file_path))
            except SyntaxError as e:
                logger.warning(f"Syntax error in {rel_path}: {e}")
                return {"file": rel_path, "status": "syntax_error", "error": str(e)}

            import hashlib

            ast_json = json.dumps(ast.dump(tree))
            ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

            try:
                # NOTE: save_ast_tree is intentionally synchronous. We must not create
                # nested event loops inside queue workers / async contexts.
                logger.debug(
                    f"Saving AST for {rel_path}, file_id={file_id}, project_id={project_id}"
                )
                ast_tree_id = database.save_ast_tree(
                    file_id,
                    project_id,
                    ast_json,
                    ast_hash,
                    file_mtime,
                    overwrite=True,
                )
                logger.debug(f"AST saved with id={ast_tree_id} for file_id={file_id}")
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
                # NOTE: save_cst_tree is intentionally synchronous. We must not create
                # nested event loops inside queue workers / async contexts.
                logger.debug(
                    f"Saving CST for {rel_path}, file_id={file_id}, project_id={project_id}"
                )
                cst_tree_id = database.save_cst_tree(
                    file_id,
                    project_id,
                    file_content,
                    cst_hash,
                    file_mtime,
                    overwrite=True,
                )
                logger.debug(f"CST saved with id={cst_tree_id} for file_id={file_id}")
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
            usages_added = 0

            class_nodes: dict[ast.ClassDef, int] = {}

            # Add module-level content to full-text search (entire file content).
            # This provides a guaranteed baseline for `fulltext_search` even if
            # per-entity extraction is partial.
            try:
                module_docstring = ast.get_docstring(tree)
            except Exception:
                module_docstring = None
            try:
                database.add_code_content(
                    file_id=file_id,
                    entity_type="file",
                    entity_name=str(rel_path),
                    content=file_content,
                    docstring=module_docstring,
                    entity_id=file_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to add file content to FTS for %s: %s",
                    rel_path,
                    e,
                    exc_info=True,
                )

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

                    # Store class content for full-text search.
                    try:
                        class_src = ast.get_source_segment(file_content, node)
                        database.add_code_content(
                            file_id=file_id,
                            entity_type="class",
                            entity_name=node.name,
                            content=class_src or "",
                            docstring=docstring,
                            entity_id=class_id,
                        )
                    except Exception as e:
                        logger.debug(
                            "Failed to add class content to FTS (%s.%s): %s",
                            rel_path,
                            node.name,
                            e,
                            exc_info=True,
                        )

                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_docstring = self._extract_docstring(item)
                            method_args = self._extract_args(item)
                            # Calculate cyclomatic complexity
                            try:
                                method_complexity = calculate_complexity(item)
                            except Exception as e:
                                logger.debug(
                                    "Failed to calculate complexity for method %s.%s: %s",
                                    node.name,
                                    item.name,
                                    e,
                                )
                                method_complexity = None
                            method_id = database.add_method(
                                class_id,
                                item.name,
                                item.lineno,
                                method_args,
                                method_docstring,
                                complexity=method_complexity,
                            )
                            methods_added += 1

                            # Store method content for full-text search.
                            try:
                                method_src = ast.get_source_segment(file_content, item)
                                database.add_code_content(
                                    file_id=file_id,
                                    entity_type="method",
                                    entity_name=f"{node.name}.{item.name}",
                                    content=method_src or "",
                                    docstring=method_docstring,
                                    entity_id=method_id,
                                )
                            except Exception as e:
                                logger.debug(
                                    "Failed to add method content to FTS (%s.%s.%s): %s",
                                    rel_path,
                                    node.name,
                                    item.name,
                                    e,
                                    exc_info=True,
                                )

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
                        # Calculate cyclomatic complexity
                        try:
                            function_complexity = calculate_complexity(node)
                        except Exception as e:
                            logger.debug(
                                "Failed to calculate complexity for function %s: %s",
                                node.name,
                                e,
                            )
                            function_complexity = None
                        function_id = database.add_function(
                            file_id,
                            node.name,
                            node.lineno,
                            args,
                            docstring,
                            complexity=function_complexity,
                        )
                        functions_added += 1

                        # Store function content for full-text search.
                        try:
                            func_src = ast.get_source_segment(file_content, node)
                            database.add_code_content(
                                file_id=file_id,
                                entity_type="function",
                                entity_name=node.name,
                                content=func_src or "",
                                docstring=docstring,
                                entity_id=function_id,
                            )
                        except Exception as e:
                            logger.debug(
                                "Failed to add function content to FTS (%s.%s): %s",
                                rel_path,
                                node.name,
                                e,
                                exc_info=True,
                            )

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

            # Track usages (function calls, method calls, class instantiations)
            try:
                from ..core.usage_tracker import UsageTracker

                def add_usage_callback(usage_record: Dict[str, Any]) -> None:
                    """Callback to add usage record to database."""
                    nonlocal usages_added
                    try:
                        database.add_usage(
                            file_id=file_id,
                            line=usage_record["line"],
                            usage_type=usage_record["usage_type"],
                            target_type=usage_record["target_type"],
                            target_name=usage_record["target_name"],
                            target_class=usage_record.get("target_class"),
                            context=usage_record.get("context"),
                        )
                        usages_added += 1
                    except Exception as e:
                        logger.debug(
                            f"Failed to add usage for {usage_record.get('target_name')} "
                            f"at line {usage_record.get('line')}: {e}",
                            exc_info=True,
                        )

                usage_tracker = UsageTracker(add_usage_callback)
                usage_tracker.visit(tree)
                logger.debug(
                    f"Tracked {usages_added} usages in {rel_path}",
                )
            except Exception as e:
                logger.warning(
                    f"Failed to track usages for {rel_path}: {e}",
                    exc_info=True,
                )
                # Continue even if usage tracking fails

            database.mark_file_needs_chunking(rel_path, project_id)

            return {
                "file": rel_path,
                "status": "success",
                "classes": classes_added,
                "functions": functions_added,
                "methods": methods_added,
                "imports": imports_added,
                "usages": usages_added,
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
        project_id: str,
        max_lines: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute code index update.

        Notes:
            Uses project_id to resolve project root from the shared database.
            If the database is detected as corrupted, this command will create a
            filesystem backup, write a persistent corruption marker, stop workers,
            and return an error. The project is then in "safe mode" until explicit
            repair/restore.

        Args:
            self: Command instance.
            project_id: Project UUID (from create_project or list_projects). Required.
            max_lines: Maximum lines per file threshold (for reporting).
                If None, uses DEFAULT_MAX_FILE_LINES from constants.
            **kwargs: Extra parameters (may include 'context' with ProgressTracker).

        Returns:
            SuccessResult with update results or ErrorResult on failure.
        """
        if max_lines is None:
            max_lines = DEFAULT_MAX_FILE_LINES

        from ..core.progress_tracker import get_progress_tracker_from_context

        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )

        try:
            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description("Resolving project...")
                progress_tracker.set_progress(0)

            database = self._open_database_from_config(auto_analyze=False)
            try:
                project = database.get_project(project_id)
                if not project or not project.root_path:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
                root_path = Path(project.root_path)
                if not root_path.exists() or not root_path.is_dir():
                    return ErrorResult(
                        message=(
                            f"Project root path does not exist or is not a directory: {root_path}"
                        ),
                        code="PROJECT_ROOT_NOT_FOUND",
                        details={"project_id": project_id, "root_path": str(root_path)},
                    )

                if progress_tracker:
                    progress_tracker.set_description("Scanning for Python files...")
                    progress_tracker.set_progress(0)

                python_files: list[Path] = []
                # Build ignore set from constants
                ignore_dirs = DEFAULT_IGNORE_PATTERNS | {DATA_DIR_NAME, LOGS_DIR_NAME}
                for walk_root, dirs, files in os.walk(root_path):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".") and d not in ignore_dirs
                    ]
                    for file in files:
                        if file.endswith(".py"):
                            python_files.append(Path(walk_root) / file)

                files_total = len(python_files)
                trigger = kwargs.get("trigger") or "manual"
                # Log update_indexes start for correlation with status snapshots (see docs/WORKER_AND_DB_STATUS_ANALYSIS.md)
                logger.info(
                    "[update_indexes START] project_id=%s files_total=%s root_path=%s trigger=%s",
                    project_id,
                    files_total,
                    str(root_path),
                    trigger,
                )
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
                            "project_id": project_id,
                            "root_path": str(root_path),
                            "files_processed": 0,
                            "files_total": 0,
                            "files_discovered": 0,
                            "errors": 0,
                            "syntax_errors": 0,
                            "classes": 0,
                            "functions": 0,
                            "methods": 0,
                            "imports": 0,
                            "db_repaired": False,
                            "db_backup_paths": [],
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

                error_details = [
                    {
                        "file": r.get("file", ""),
                        "error": r.get("error", "Unknown"),
                        "error_type": r.get("error_type", "Unknown"),
                    }
                    for r in results
                    if r.get("status") == "error"
                ]

                if progress_tracker:
                    progress_tracker.set_progress(100)
                    progress_tracker.set_description("Indexing completed")
                    progress_tracker.set_status("completed")

                # Log update_indexes end for correlation with status snapshots
                logger.info(
                    "[update_indexes END] project_id=%s files_processed=%s files_total=%s errors=%s trigger=%s",
                    project_id,
                    successful,
                    total,
                    errors,
                    trigger,
                )

                data: Dict[str, Any] = {
                    "project_id": project_id,
                    "root_path": str(root_path),
                    "files_processed": successful,
                    "files_total": total,
                    "files_discovered": files_total,
                    "errors": errors,
                    "syntax_errors": syntax_errors,
                    "classes": total_classes,
                    "functions": total_functions,
                    "methods": total_methods,
                    "imports": total_imports,
                    "db_repaired": False,
                    "db_backup_paths": [],
                    "workers_restarted": {},
                    "message": (
                        f"Indexes updated: {successful}/{total} files processed, "
                        f"{errors} errors, {syntax_errors} syntax errors"
                    ),
                }
                if error_details:
                    data["error_details"] = error_details

                return SuccessResult(data=data)
            finally:
                database.disconnect()

        except Exception as e:
            if progress_tracker:
                progress_tracker.set_status("failed")
            return self._handle_error(e, "INDEX_UPDATE_ERROR", "update_indexes")

    @classmethod
    def metadata(cls: type["UpdateIndexesMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The update_indexes command analyzes Python project files and updates code indexes "
                "in the SQLite database. This is a long-running command executed via queue that "
                "parses Python files, extracts code entities, and stores them in the database for "
                "fast retrieval and analysis.\n\n"
                "Operation flow:\n"
                "1. Resolves project root_path from shared database by project_id\n"
                "2. Validates root_path exists and is a directory\n"
                "3. Checks database integrity (if corrupted, enters safe mode)\n"
                "4. Scans root_path for Python files (excludes .git, __pycache__, node_modules, data, logs)\n"
                "5. For each Python file:\n"
                "   - Reads file content and parses AST\n"
                "   - Saves AST tree to database\n"
                "   - Saves CST (source code) to database\n"
                "   - Extracts classes, functions, methods, imports\n"
                "   - Calculates cyclomatic complexity for functions/methods\n"
                "   - Stores entities in database\n"
                "   - Adds content to full-text search index\n"
                "   - Marks file for chunking\n"
                "6. Updates progress tracker during processing\n"
                "7. Returns summary statistics\n\n"
                "Database Safety:\n"
                "- Checks database integrity before starting\n"
                "- If corruption detected:\n"
                "  - Creates backup of database files\n"
                "  - Writes corruption marker\n"
                "  - Stops workers\n"
                "  - Enters safe mode (only backup/restore/repair commands allowed)\n"
                "- Returns error if database is in safe mode\n\n"
                "Indexed Information:\n"
                "- Files: Path, line count, modification time, docstring status\n"
                "- Classes: Name, line, docstring, base classes\n"
                "- Functions: Name, line, parameters, docstring, complexity\n"
                "- Methods: Name, line, parameters, docstring, complexity, class context\n"
                "- Imports: Module, name, type, line\n"
                "- AST trees: Full AST JSON for each file\n"
                "- CST trees: Full source code for each file\n"
                "- Full-text search: Code content indexed for search\n\n"
                "Use cases:\n"
                "- Initial project indexing\n"
                "- Re-indexing after code changes\n"
                "- Updating indexes after adding new files\n"
                "- Rebuilding database indexes\n\n"
                "Important notes:\n"
                "- This is a long-running command (use_queue=True)\n"
                "- Progress is tracked and can be monitored via queue_get_job_status\n"
                "- Skips files with syntax errors (continues with other files)\n"
                "- Files are processed sequentially\n"
                "- Database must not be corrupted (check integrity first)\n"
                "- Excludes hidden directories and common build/cache directories"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID from create_project or list_projects. "
                        "Root path is resolved from the shared database."
                    ),
                    "type": "string",
                    "required": True,
                },
                "max_lines": {
                    "description": (
                        "Maximum lines per file threshold. Default is 400. "
                        "Used for reporting long files (does not affect indexing)."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 400,
                },
            },
            "usage_examples": [
                {
                    "description": "Update indexes for project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": (
                        "Resolves project root from database by project_id, then analyzes "
                        "all Python files and updates indexes. Long-running; use queue_get_job_status to check progress."
                    ),
                },
                {
                    "description": "Update indexes with custom line threshold",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "max_lines": 500,
                    },
                    "explanation": (
                        "Updates indexes and uses 500 lines as threshold for long file reporting."
                    ),
                },
            ],
            "error_cases": {
                "DATABASE_CORRUPTED": {
                    "description": "Database is corrupted and in safe mode",
                    "example": "Database integrity check failed or corruption marker exists",
                    "solution": (
                        "Database is in safe mode. Run repair_sqlite_database (force=true) "
                        "or restore_database from backup, then re-run update_indexes."
                    ),
                },
                "INDEX_UPDATE_ERROR": {
                    "description": "General error during index update",
                    "example": "File access error, AST parsing error, or database error",
                    "solution": (
                        "Check file permissions, verify Python files are valid, check database integrity. "
                        "Syntax errors in files are skipped automatically."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "project_id": "Project UUID",
                        "root_path": "Project root path that was analyzed (from database)",
                        "files_processed": "Number of files successfully processed",
                        "files_total": "Total number of files analyzed",
                        "files_discovered": "Total number of Python files discovered",
                        "errors": "Number of files with errors",
                        "syntax_errors": "Number of files with syntax errors",
                        "classes": "Total number of classes indexed",
                        "functions": "Total number of functions indexed",
                        "methods": "Total number of methods indexed",
                        "imports": "Total number of imports indexed",
                        "db_repaired": "Whether database was repaired (always False)",
                        "db_backup_paths": "List of backup paths (empty if no backup)",
                        "workers_restarted": "Dictionary of restarted workers (empty)",
                        "message": "Summary message",
                    },
                    "example": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "root_path": "/home/user/projects/my_project",
                        "files_processed": 42,
                        "files_total": 45,
                        "files_discovered": 45,
                        "errors": 2,
                        "syntax_errors": 1,
                        "classes": 25,
                        "functions": 50,
                        "methods": 100,
                        "imports": 200,
                        "db_repaired": False,
                        "db_backup_paths": [],
                        "workers_restarted": {},
                        "message": "Indexes updated: 42/45 files processed, 2 errors, 1 syntax errors",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., DATABASE_CORRUPTED, INDEX_UPDATE_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error details (e.g., db_path, marker_path, backup_paths)",
                },
            },
            "best_practices": [
                "Run this command after adding new files or making significant code changes",
                "Use queue_get_job_status to monitor progress for large projects",
                "Check database integrity before running (use get_database_corruption_status)",
                "Run regularly to keep indexes up-to-date",
                "If database is corrupted, repair or restore before re-indexing",
                "Review error counts in results to identify problematic files",
                "This command is required before using most other analysis commands",
            ],
        }
