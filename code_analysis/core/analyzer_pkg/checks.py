"""
Module checks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import json
import hashlib
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _has_file_docstring(self, tree: ast.Module) -> bool:
    """Check if file has a docstring."""
    if not tree.body:
        return False

    first_node = tree.body[0]
    return (
        isinstance(first_node, ast.Expr)
        and isinstance(first_node.value, ast.Constant)
        and isinstance(first_node.value.value, str)
    )


def _has_pass_statement(self, node: ast.FunctionDef) -> bool:
    """Check if function has only pass statement."""
    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
        return True
    return False


def _has_not_implemented_error(self, node: ast.FunctionDef) -> bool:
    """Check if function raises NotImplementedError."""
    for stmt in node.body:
        if isinstance(stmt, ast.Raise):
            if isinstance(stmt.exc, ast.Call):
                if (
                    isinstance(stmt.exc.func, ast.Name)
                    and stmt.exc.func.id == "NotImplementedError"
                ):
                    return True
    return False


def _is_abstract_method(self, node: ast.FunctionDef) -> bool:
    """Check if method is abstract."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
            return True
    return False


async def _save_ast_tree(
    self,
    tree: ast.Module,
    file_id: int,
    project_id: str,
    file_mtime: float,
    force: bool = False,
) -> bool:
    """
    Save AST tree to database with time check.

    Args:
        tree: AST module node
        file_id: File ID in database
        project_id: Project ID
        file_mtime: File modification time
        force: If True, save regardless of time check

    Returns:
        True if AST was saved, False if skipped (not outdated)
    """
    if not self.database:
        return False

    try:
        # Check if AST is outdated (unless force is True)
        if not force:
            if not self.database.is_ast_outdated(file_id, file_mtime):
                logger.debug(f"AST tree for file_id={file_id} is up to date, skipping")
                return False

        # Convert AST to JSON-serializable format
        ast_dict = self._ast_to_dict(tree)

        # Serialize to JSON
        ast_json = json.dumps(ast_dict, indent=2)

        # Calculate hash for change detection
        ast_hash = hashlib.sha256(ast_json.encode("utf-8")).hexdigest()

        # Save to database (overwrite existing)
        await self.database.overwrite_ast_tree(
            file_id=file_id,
            project_id=project_id,
            ast_json=ast_json,
            ast_hash=ast_hash,
            file_mtime=file_mtime,
        )

        logger.debug(f"Saved AST tree for file_id={file_id}, mtime={file_mtime}")
        return True
    except Exception as e:
        logger.error(f"Error saving AST tree for file_id={file_id}: {e}")
        return False


def _ast_to_dict(self, node: ast.AST) -> Dict[str, Any]:
    """
    Convert AST node to dictionary.

    Args:
        node: AST node

    Returns:
        Dictionary representation of AST node
    """
    if isinstance(node, ast.AST):
        result = {
            "_type": type(node).__name__,
        }
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                result[field] = [self._ast_to_dict(item) for item in value]
            elif isinstance(value, ast.AST):
                result[field] = self._ast_to_dict(value)
            elif value is Ellipsis or value is ...:
                # Handle ellipsis (...) which is not JSON serializable
                result[field] = None
            else:
                result[field] = value
        return result
    elif isinstance(node, list):
        return [self._ast_to_dict(item) for item in node]
    elif node is Ellipsis or node is ...:
        # Handle ellipsis (...) which is not JSON serializable
        return None
    else:
        return node
