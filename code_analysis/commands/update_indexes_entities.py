"""
Entity extraction and DB indexing for update_indexes (classes, methods, functions, imports).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from typing import Any, Dict, Tuple

from ..core.complexity_analyzer import calculate_complexity

logger = logging.getLogger(__name__)


def _extract_docstring(node: ast.AST) -> str | None:
    """Extract docstring from an AST node."""
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


def _extract_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract argument names from function node, excluding 'self'."""
    args: list[str] = []
    for arg in node.args.args:
        if arg.arg != "self":
            args.append(arg.arg)
    return args


def index_entities(
    database: Any,
    file_id: int,
    tree: ast.Module,
    file_content: str,
    rel_path: str,
) -> Tuple[int, int, int, int]:
    """Index classes, methods, top-level functions, and imports. O(n) over AST.

    Precomputes method node ids from class bodies for O(1) function vs method
    classification. Returns (classes_added, functions_added, methods_added, imports_added).

    Args:
        database: DatabaseClient instance.
        file_id: File ID.
        tree: Parsed AST.
        file_content: Source code for get_source_segment.
        rel_path: Relative path for logging.

    Returns:
        Tuple of (classes_added, functions_added, methods_added, imports_added).
    """
    classes_added = 0
    functions_added = 0
    methods_added = 0
    imports_added = 0

    class_nodes: Dict[ast.ClassDef, int] = {}
    method_node_ids: set[int] = set()

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
            docstring = _extract_docstring(node)
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
                    method_node_ids.add(id(item))
                    method_docstring = _extract_docstring(item)
                    method_args = _extract_args(item)
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
            if id(node) in method_node_ids:
                continue
            docstring = _extract_docstring(node)
            args = _extract_args(node)
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
                database.add_import(file_id, alias.name, None, "import", node.lineno)
                imports_added += 1
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                database.add_import(
                    file_id, alias.name, module, "import_from", node.lineno
                )
                imports_added += 1

    return (classes_added, functions_added, methods_added, imports_added)
