"""
Build and run batch SQL for updating file data (AST, CST, entities).

Replaces per-row save_ast/save_cst/create_class/create_method/create_function/
create_import with execute_batch to minimize DB round-trips.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from .objects.class_function import Class, Function
from .objects.method_import import Import, Method

logger = logging.getLogger(__name__)


def _row_to_insert_sql(table: str, row: Dict[str, Any]) -> Tuple[str, tuple]:
    """Build (sql, params) for INSERT from row dict; exclude id for new rows."""
    data = {k: v for k, v in row.items() if k != "id"}
    if not data:
        raise ValueError(f"Empty row for table {table}")
    cols = list(data.keys())
    vals = tuple(data.values())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    return (sql, vals)


def update_file_data_atomic_batch(
    database: Any,
    file_id: int,
    project_id: str,
    source_code: str,
    file_path: str,
    file_mtime: float,
    transaction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update all file data (AST, CST, classes, methods, functions, imports) via batch.

    Runs 3 execute_batch calls: (1) clear + ast + cst, (2) insert classes,
    (3) insert methods + functions + imports. Order preserved; minimizes write commands.
    """
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s: %s", file_path, e)
        return {
            "success": False,
            "error": f"Syntax error: {e}",
            "file_path": file_path,
            "file_id": file_id,
        }
    except Exception as e:
        logger.error("Error parsing AST for %s: %s", file_path, e, exc_info=True)
        return {
            "success": False,
            "error": f"Failed to parse AST: {e}",
            "file_path": file_path,
            "file_id": file_id,
        }

    ast_dump = ast.dump(tree)
    ast_data = ast_dump if isinstance(ast_dump, dict) else {"ast": ast_dump}
    ast_json = json.dumps(ast_data)
    ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
    cst_hash = hashlib.sha256(source_code.encode()).hexdigest()

    # Batch 1: clear file's entities + insert ast + insert cst
    ops1: List[Tuple[str, Optional[tuple]]] = [
        (
            "DELETE FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id = ?)",
            (file_id,),
        ),
        ("DELETE FROM classes WHERE file_id = ?", (file_id,)),
        ("DELETE FROM ast_trees WHERE file_id = ?", (file_id,)),
        ("DELETE FROM cst_trees WHERE file_id = ?", (file_id,)),
        ("DELETE FROM functions WHERE file_id = ?", (file_id,)),
        ("DELETE FROM imports WHERE file_id = ?", (file_id,)),
        (
            "INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime) VALUES (?, ?, ?, ?, ?)",
            (file_id, project_id, ast_json, ast_hash, file_mtime),
        ),
        (
            "INSERT INTO cst_trees (file_id, project_id, cst_code, cst_hash, file_mtime) VALUES (?, ?, ?, ?, ?)",
            (file_id, project_id, source_code, cst_hash, file_mtime),
        ),
    ]
    results1 = database.execute_batch(ops1, transaction_id)
    if len(results1) < 8:
        return {
            "success": False,
            "error": f"execute_batch (clear+ast+cst) returned {len(results1)} results",
            "file_path": file_path,
            "file_id": file_id,
        }

    # Extract classes and methods (with class index for later class_id mapping)
    class_rows: List[Dict[str, Any]] = []
    method_specs: List[Tuple[int, Dict[str, Any]]] = []  # (class_index, row)
    function_rows: List[Dict[str, Any]] = []
    import_rows: List[Dict[str, Any]] = []

    class_nodes_ordered: List[ast.ClassDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            docstring = ast.get_docstring(node)
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                else:
                    try:
                        bases.append(ast.unparse(base))
                    except AttributeError:
                        bases.append(str(base))
            class_obj = Class(
                file_id=file_id,
                name=node.name,
                line=node.lineno,
                docstring=docstring,
                bases=bases,
            )
            row = class_obj.to_db_row()
            row.pop("id", None)
            row.pop("created_at", None)
            class_rows.append(row)
            class_nodes_ordered.append(node)
            idx = len(class_rows) - 1
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_docstring = ast.get_docstring(item)
                    method_args = []
                    if item.args:
                        for arg in item.args.args:
                            arg_name = arg.arg
                            if arg.annotation:
                                try:
                                    arg_name += f": {ast.unparse(arg.annotation)}"
                                except AttributeError:
                                    arg_name += f": {str(arg.annotation)}"
                            method_args.append(arg_name)
                    method_obj = Method(
                        class_id=0,
                        name=item.name,
                        line=item.lineno,
                        docstring=method_docstring,
                        args=method_args,
                    )
                    row = method_obj.to_db_row()
                    row.pop("id", None)
                    row.pop("created_at", None)
                    method_specs.append((idx, row))

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
            if is_method:
                continue
            docstring = ast.get_docstring(node)
            args = []
            if node.args:
                for arg in node.args.args:
                    arg_name = arg.arg
                    if arg.annotation:
                        try:
                            arg_name += f": {ast.unparse(arg.annotation)}"
                        except AttributeError:
                            arg_name += f": {str(arg.annotation)}"
                    args.append(arg_name)
            func_obj = Function(
                file_id=file_id,
                name=node.name,
                line=node.lineno,
                docstring=docstring,
                args=args,
            )
            row = func_obj.to_db_row()
            row.pop("id", None)
            row.pop("created_at", None)
            function_rows.append(row)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imp = Import(
                    file_id=file_id,
                    module="",
                    name=alias.name,
                    import_type="import",
                    line=node.lineno,
                )
                row = imp.to_db_row()
                row.pop("id", None)
                row.pop("created_at", None)
                import_rows.append(row)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imp = Import(
                    file_id=file_id,
                    module=module,
                    name=alias.name,
                    import_type="from",
                    line=node.lineno,
                )
                row = imp.to_db_row()
                row.pop("id", None)
                row.pop("created_at", None)
                import_rows.append(row)

    # Batch 2: insert classes
    if not class_rows:
        class_lastrowids: List[int] = []
    else:
        ops2 = [_row_to_insert_sql("classes", r) for r in class_rows]
        results2 = database.execute_batch(ops2, transaction_id)
        class_lastrowids = [(r.get("lastrowid") or 0) for r in results2]

    # Batch 3: insert methods (with class_id from batch2) + functions + imports
    ops3: List[Tuple[str, tuple]] = []
    for class_idx, row in method_specs:
        row = dict(row)
        if class_idx < len(class_lastrowids):
            row["class_id"] = class_lastrowids[class_idx]
        ops3.append(_row_to_insert_sql("methods", row))
    for row in function_rows:
        ops3.append(_row_to_insert_sql("functions", row))
    for row in import_rows:
        ops3.append(_row_to_insert_sql("imports", row))

    if ops3:
        database.execute_batch(ops3, transaction_id)

    return {
        "success": True,
        "file_id": file_id,
        "file_path": file_path,
        "ast_updated": True,
        "cst_updated": True,
        "entities_updated": len(class_rows)
        + len(method_specs)
        + len(function_rows)
        + len(import_rows),
        "classes": len(class_rows),
        "functions": len(function_rows),
        "methods": len(method_specs),
        "imports": len(import_rows),
    }
