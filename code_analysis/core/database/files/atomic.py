"""
File atomic update: update_file_data_atomic (in-transaction update).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def update_file_data_atomic(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
    source_code: str,
    file_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Atomically update all file data in a transaction.

    IMPORTANT: Must be called within an active transaction.
    This method updates AST, CST, and entities for a file using source_code directly.

    Process:
    1. Find file_id by path
    2. Clear all old records (AST, CST, entities) in transaction
    3. Parse entire file from source_code
    4. Save AST tree in transaction
    5. Save CST tree in transaction
    6. Extract and save entities (classes, functions, methods, imports) in transaction
    7. Return result

    Args:
        file_path: File path (relative to root_dir or absolute)
        project_id: Project ID
        root_dir: Project root directory
        source_code: Full source code of the file (for parsing entire file)

    Returns:
        Dictionary with update result:
        {
            "success": bool,
            "file_id": int,
            "file_path": str,
            "ast_updated": bool,
            "cst_updated": bool,
            "entities_updated": int,
            "error": Optional[str]
        }

    Raises:
        RuntimeError: If not called within an active transaction
    """
    from ...path_normalization import normalize_path_simple
    from ...exceptions import ProjectIdMismatchError

    # Check that we're in a transaction
    if not self._in_transaction():
        raise RuntimeError(
            "update_file_data_atomic must be called within a transaction"
        )

    try:
        # If file_id is provided, use it directly (useful when file was just added in transaction)
        if file_id is not None:
            file_record = self.get_file_by_id(file_id)
            if not file_record:
                return {
                    "success": False,
                    "error": f"File not found in database by file_id: {file_id}",
                    "file_path": file_path,
                }
            abs_path = file_record.get("path") or file_path
        else:
            # Normalize path to absolute
            abs_path = normalize_path_simple(file_path)

            # Get file record
            file_record = self.get_file_by_path(abs_path, project_id)
            if not file_record:
                return {
                    "success": False,
                    "error": f"File not found in database: {file_path}",
                    "file_path": abs_path,
                }

            file_id = file_record["id"]

        # Clear all old records in transaction
        try:
            self.clear_file_data(file_id)
        except Exception as e:
            logger.error(
                f"Error clearing file data for {file_path}: {e}", exc_info=True
            )
            return {
                "success": False,
                "error": f"Failed to clear old records: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Parse AST from source_code
        try:
            from ...ast_utils import parse_with_comments

            tree = parse_with_comments(source_code, filename=abs_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return {
                "success": False,
                "error": f"Syntax error: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }
        except Exception as e:
            logger.error(f"Error parsing AST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to parse AST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Calculate file metadata
        import time

        file_mtime = time.time()  # Use current time as mtime for atomic update

        # Save AST tree in transaction
        import hashlib
        import json

        ast_json = json.dumps(ast.dump(tree))
        ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

        try:
            ast_tree_id = self.save_ast_tree(
                file_id,
                project_id,
                ast_json,
                ast_hash,
                file_mtime,
                overwrite=True,
            )
            logger.debug(f"AST saved with id={ast_tree_id} for file_id={file_id}")
        except Exception as e:
            logger.error(f"Error saving AST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to save AST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Build in-memory CST tree for entity-to-node resolution (cst_node_id).
        from ...cst_tree.tree_builder import create_tree_from_code
        from ...cst_tree.tree_range_finder import find_node_by_range

        try:
            cst_tree = create_tree_from_code(abs_path, source_code)
        except Exception as e:
            logger.error(f"Error building CST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to build CST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Save CST tree in transaction
        cst_hash = hashlib.sha256(source_code.encode()).hexdigest()
        try:
            cst_tree_id = self.save_cst_tree(
                file_id,
                project_id,
                source_code,
                cst_hash,
                file_mtime,
                overwrite=True,
            )
            logger.debug(f"CST saved with id={cst_tree_id} for file_id={file_id}")
        except Exception as e:
            logger.error(f"Error saving CST for {file_path}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to save CST: {e}",
                "file_path": abs_path,
                "file_id": file_id,
            }

        # Extract and save entities in transaction
        from ....commands.update_indexes_entities import (
            _extract_docstring,
            _extract_args,
        )

        classes_added = 0
        functions_added = 0
        methods_added = 0
        imports_added = 0
        usages_added = 0

        class_nodes: Dict[ast.ClassDef, int] = {}

        # Add module-level content to full-text search
        try:
            module_docstring = ast.get_docstring(tree)
        except Exception:
            module_docstring = None
        try:
            self.add_code_content(
                file_id=file_id,
                entity_type="file",
                entity_name=str(abs_path),
                content=source_code,
                docstring=module_docstring,
                entity_id=file_id,
            )
        except Exception as e:
            logger.warning(
                f"Failed to add file content to FTS for {abs_path}: {e}",
                exc_info=True,
            )

        # Extract classes and methods
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                docstring = _extract_docstring(node)
                bases: List[str] = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    else:
                        try:
                            bases.append(ast.unparse(base))
                        except AttributeError:
                            bases.append(str(base))
                end_line_class = getattr(node, "end_lineno", node.lineno)
                class_cst_node = find_node_by_range(
                    cst_tree.tree_id,
                    node.lineno,
                    end_line_class,
                    prefer_exact=True,
                )
                if not class_cst_node:
                    raise ValueError(
                        f"No CST node found for class {node.name!r} at line {node.lineno}-{end_line_class} in {abs_path}"
                    )
                class_id = self.add_class(
                    file_id,
                    node.name,
                    node.lineno,
                    docstring,
                    bases,
                    end_line=end_line_class,
                    cst_node_id=class_cst_node.stable_id,
                )
                classes_added += 1
                class_nodes[node] = class_id

                # Store class content for full-text search
                try:
                    class_src = ast.get_source_segment(source_code, node)
                    self.add_code_content(
                        file_id=file_id,
                        entity_type="class",
                        entity_name=node.name,
                        content=class_src or "",
                        docstring=docstring,
                        entity_id=class_id,
                    )
                except Exception as e:
                    logger.debug(
                        f"Failed to add class content to FTS ({abs_path}.{node.name}): {e}",
                        exc_info=True,
                    )

                # Extract methods from class
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_docstring = _extract_docstring(item)
                        method_args = _extract_args(item)
                        # Calculate cyclomatic complexity
                        try:
                            from ...complexity_analyzer import calculate_complexity

                            method_complexity = calculate_complexity(item)
                        except Exception as e:
                            logger.debug(
                                f"Failed to calculate complexity for method {node.name}.{item.name}: {e}",
                                exc_info=True,
                            )
                            method_complexity = None
                        end_line_method = getattr(item, "end_lineno", item.lineno)
                        method_cst_node = find_node_by_range(
                            cst_tree.tree_id,
                            item.lineno,
                            end_line_method,
                            prefer_exact=True,
                        )
                        if not method_cst_node:
                            raise ValueError(
                                f"No CST node found for method {node.name!r}.{item.name!r} at line {item.lineno}-{end_line_method} in {abs_path}"
                            )
                        method_id = self.add_method(
                            class_id,
                            item.name,
                            item.lineno,
                            method_args,
                            method_docstring,
                            complexity=method_complexity,
                            end_line=end_line_method,
                            cst_node_id=method_cst_node.stable_id,
                        )
                        methods_added += 1

                        # Store method content for full-text search
                        try:
                            method_src = ast.get_source_segment(source_code, item)
                            self.add_code_content(
                                file_id=file_id,
                                entity_type="method",
                                entity_name=f"{node.name}.{item.name}",
                                content=method_src or "",
                                docstring=method_docstring,
                                entity_id=method_id,
                            )
                        except Exception as e:
                            logger.debug(
                                f"Failed to add method content to FTS ({abs_path}.{node.name}.{item.name}): {e}",
                                exc_info=True,
                            )

        # Extract top-level functions
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_method = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef):
                        if any(
                            node == item
                            for item in parent.body
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ):
                            is_method = True
                            break

                if not is_method:
                    docstring = _extract_docstring(node)
                    args = _extract_args(node)
                    # Calculate cyclomatic complexity
                    try:
                        from ...complexity_analyzer import calculate_complexity

                        function_complexity = calculate_complexity(node)
                    except Exception as e:
                        logger.debug(
                            f"Failed to calculate complexity for function {node.name}: {e}",
                            exc_info=True,
                        )
                        function_complexity = None
                    end_line_func = getattr(node, "end_lineno", node.lineno)
                    function_cst_node = find_node_by_range(
                        cst_tree.tree_id,
                        node.lineno,
                        end_line_func,
                        prefer_exact=True,
                    )
                    if not function_cst_node:
                        raise ValueError(
                            f"No CST node found for function {node.name!r} at line {node.lineno}-{end_line_func} in {abs_path}"
                        )
                    function_id = self.add_function(
                        file_id,
                        node.name,
                        node.lineno,
                        args,
                        docstring,
                        complexity=function_complexity,
                        end_line=end_line_func,
                        cst_node_id=function_cst_node.stable_id,
                    )
                    functions_added += 1

                    # Store function content for full-text search
                    try:
                        function_src = ast.get_source_segment(source_code, node)
                        self.add_code_content(
                            file_id=file_id,
                            entity_type="function",
                            entity_name=node.name,
                            content=function_src or "",
                            docstring=docstring,
                            entity_id=function_id,
                        )
                    except Exception as e:
                        logger.debug(
                            f"Failed to add function content to FTS ({abs_path}.{node.name}): {e}",
                            exc_info=True,
                        )

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.add_import(file_id, alias.name, None, "import", node.lineno)
                    imports_added += 1
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    self.add_import(file_id, alias.name, module, "from", node.lineno)
                    imports_added += 1

        # Track usages (function calls, method calls, class instantiations)
        try:
            from ...usage_tracker import UsageTracker

            def add_usage_callback(usage_record: Dict[str, Any]) -> None:
                """Callback to add usage record to database."""
                nonlocal usages_added
                try:
                    self.add_usage(
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
                f"Tracked {usages_added} usages in {abs_path}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to track usages for {abs_path}: {e}",
                exc_info=True,
            )
            # Continue even if usage tracking fails

        # Build entity cross-ref from usages (caller/callee by entity id)
        try:
            from ...entity_cross_ref_builder import build_entity_cross_ref_for_file

            cross_ref_added = build_entity_cross_ref_for_file(
                self, file_id, project_id, source_code
            )
            logger.debug(
                f"Built {cross_ref_added} entity cross-refs for {abs_path}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to build entity cross-ref for {abs_path}: {e}",
                exc_info=True,
            )
            # Do not fail the whole file update

        entities_count = classes_added + functions_added + methods_added

        # Clear indexing error for this file on successful write
        try:
            self._execute(
                "DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?",
                (project_id, abs_path),
            )
            self._commit()
        except Exception:
            pass

        return {
            "success": True,
            "file_id": file_id,
            "file_path": abs_path,
            "ast_updated": True,
            "cst_updated": True,
            "entities_updated": entities_count,
            "classes": classes_added,
            "functions": functions_added,
            "methods": methods_added,
            "imports": imports_added,
            "usages": usages_added,
        }

    except ProjectIdMismatchError:
        # Re-raise project ID mismatch - this is a critical error
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in update_file_data_atomic for {file_path}: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "file_path": str(file_path),
        }
