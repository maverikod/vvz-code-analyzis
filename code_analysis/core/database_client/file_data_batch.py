"""
Build and run batch SQL for updating file data (AST, CST, entities).

Replaces per-row save_ast/save_cst/create_class/create_method/create_function/
create_import with one execute_logical_write_operation to minimize DB round-trips.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..database.logical_write_submit import (
    execute_all_batches_in_transaction,
    submit_logical_write_or_fallback,
)
from .objects.class_function import Class, Function
from .objects.method_import import Import, Method

logger = logging.getLogger(__name__)


def _row_to_insert_sql(table: str, row: Dict[str, Any]) -> Tuple[str, tuple]:
    """Build (sql, params) for INSERT from row dict; generates UUID ``id`` when absent."""
    data = dict(row)
    if data.get("id") is None:
        data["id"] = str(uuid.uuid4())
    if not data:
        raise ValueError(f"Empty row for table {table}")
    cols = list(data.keys())
    vals = tuple(data.values())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    return (sql, vals)


def _method_insert_sql_with_class_id(
    row: Dict[str, Any],
    class_id: str,
    method_id: str,
) -> Tuple[str, Tuple[Any, ...]]:
    """INSERT method row with explicit class UUID and method UUID."""
    data = {k: v for k, v in row.items() if k not in ("id", "class_id")}
    if not data:
        raise ValueError("Empty method row")
    cols = ["id", "class_id"] + list(data.keys())
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO methods ({', '.join(cols)}) VALUES ({placeholders})"
    params = (method_id, class_id) + tuple(data.values())
    return sql, params


def _code_content_insert_ops(
    *,
    file_id: str,
    entity_type: str,
    entity_id: Optional[str],
    entity_name: str,
    content: str,
    docstring: Optional[str],
    driver_type: Optional[str],
) -> List[Tuple[str, Any]]:
    """INSERT ``code_content`` (PostgreSQL: explicit UUID ``id``).

    ``driver_type`` is kept for call-site compatibility; only ``postgres`` is supported.
    """
    _ = driver_type
    rid = str(uuid.uuid4())
    row: Dict[str, Any] = {
        "id": rid,
        "file_id": file_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "content": content or "",
        "docstring": docstring,
    }
    sql, params = _row_to_insert_sql("code_content", row)
    return [(sql, params)]


def build_file_data_atomic_batches(
    file_id: str,
    project_id: str,
    source_code: str,
    file_path: str,
    file_mtime: float,
    *,
    driver_type: Optional[str] = None,
) -> Tuple[list[list[Tuple[str, Any]]], dict[str, Any]]:
    """
    Build ordered batches for file data update and metadata for the result dict.

    Populates ``code_content`` so
    :meth:`~code_analysis.core.database_client.client_api_search._ClientAPISearchMixin.full_text_search`
    returns matches after indexing.

    Args:
        driver_type: Kept for call-site compatibility; only ``postgres`` is supported
            (same as :attr:`~code_analysis.core.database_client.client.DatabaseClient._driver_type`).

    Returns:
        (batches, meta). On syntax error, ([], {success: False, ...}).
    """
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s: %s", file_path, e)
        return (
            [],
            {
                "success": False,
                "error": f"Syntax error: {e}",
                "file_path": file_path,
                "file_id": file_id,
            },
        )
    except Exception as e:
        logger.error("Error parsing AST for %s: %s", file_path, e, exc_info=True)
        return (
            [],
            {
                "success": False,
                "error": f"Failed to parse AST: {e}",
                "file_path": file_path,
                "file_id": file_id,
            },
        )

    # UUID file ids at runtime; entity row objects still declare legacy int annotation.
    fid_entity: Any = file_id

    ast_dump = ast.dump(tree)
    ast_data = ast_dump if isinstance(ast_dump, dict) else {"ast": ast_dump}
    ast_json = json.dumps(ast_data)
    ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
    cst_hash = hashlib.sha256(source_code.encode()).hexdigest()
    ast_row_id = str(uuid.uuid4())
    cst_row_id = str(uuid.uuid4())

    # Full-text rows (code_content) must be cleared before entity teardown.
    _ = driver_type
    code_content_deletes: List[Tuple[str, Optional[tuple]]] = [
        ("DELETE FROM code_content WHERE file_id = ?", (file_id,))
    ]

    ops1: List[Tuple[str, Optional[tuple]]] = code_content_deletes + [
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
            "INSERT INTO ast_trees (id, file_id, project_id, ast_json, ast_hash, file_mtime) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ast_row_id, file_id, project_id, ast_json, ast_hash, file_mtime),
        ),
        (
            "INSERT INTO cst_trees (id, file_id, project_id, cst_code, cst_hash, file_mtime) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cst_row_id, file_id, project_id, source_code, cst_hash, file_mtime),
        ),
    ]

    class_rows: List[Dict[str, Any]] = []
    method_specs: List[Tuple[int, Dict[str, Any], str, ast.AST]] = []
    function_rows: List[Dict[str, Any]] = []
    function_ast_nodes: List[ast.AST] = []
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
                file_id=fid_entity,
                name=node.name,
                line=node.lineno,
                docstring=docstring,
                bases=bases,
            )
            row = class_obj.to_db_row()
            row.pop("id", None)
            row.pop("created_at", None)
            row.setdefault("cst_node_id", "")
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
                    row_m = method_obj.to_db_row()
                    row_m.pop("id", None)
                    row_m.pop("created_at", None)
                    row_m.setdefault("cst_node_id", "")
                    method_specs.append((idx, row_m, str(uuid.uuid4()), item))

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
                file_id=fid_entity,
                name=node.name,
                line=node.lineno,
                docstring=docstring,
                args=args,
            )
            row = func_obj.to_db_row()
            row.pop("id", None)
            row.pop("created_at", None)
            row.setdefault("cst_node_id", "")
            function_rows.append(row)
            function_ast_nodes.append(node)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imp = Import(
                    file_id=fid_entity,
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
                    file_id=fid_entity,
                    module=module,
                    name=alias.name,
                    import_type="from",
                    line=node.lineno,
                )
                row = imp.to_db_row()
                row.pop("id", None)
                row.pop("created_at", None)
                import_rows.append(row)

    for r in class_rows:
        r["id"] = str(uuid.uuid4())

    for row in function_rows:
        row["id"] = str(uuid.uuid4())

    batches: list[list[Tuple[str, Any]]] = [ops1]

    if class_rows:
        ops2 = [_row_to_insert_sql("classes", r) for r in class_rows]
        batches.append(ops2)

    ops3: List[Tuple[str, Any]] = []
    for class_idx, row_m, method_id, _meth_ast in method_specs:
        row_d = dict(row_m)
        class_id_val = class_rows[class_idx]["id"]
        ops3.append(_method_insert_sql_with_class_id(row_d, class_id_val, method_id))
    for row in function_rows:
        ops3.append(_row_to_insert_sql("functions", row))
    for row in import_rows:
        ops3.append(_row_to_insert_sql("imports", row))

    if ops3:
        batches.append(ops3)

    ops_cc: List[Tuple[str, Any]] = []
    try:
        module_docstring = ast.get_docstring(tree)
    except Exception:
        module_docstring = None
    ops_cc.extend(
        _code_content_insert_ops(
            file_id=file_id,
            entity_type="file",
            entity_id=file_id,
            entity_name=str(file_path),
            content=source_code,
            docstring=module_docstring,
            driver_type=driver_type,
        )
    )
    for class_idx, cls_node in enumerate(class_nodes_ordered):
        cid = class_rows[class_idx]["id"]
        class_doc = ast.get_docstring(cls_node)
        class_src = ast.get_source_segment(source_code, cls_node) or ""
        ops_cc.extend(
            _code_content_insert_ops(
                file_id=file_id,
                entity_type="class",
                entity_id=cid,
                entity_name=cls_node.name,
                content=class_src,
                docstring=class_doc,
                driver_type=driver_type,
            )
        )
    for class_idx, _row_m, method_id, meth_node in method_specs:
        cls_node = class_nodes_ordered[class_idx]
        method_doc = ast.get_docstring(meth_node)
        method_src = ast.get_source_segment(source_code, meth_node) or ""
        qual = f"{cls_node.name}.{meth_node.name}"
        ops_cc.extend(
            _code_content_insert_ops(
                file_id=file_id,
                entity_type="method",
                entity_id=method_id,
                entity_name=qual,
                content=method_src,
                docstring=method_doc,
                driver_type=driver_type,
            )
        )
    for row, func_node in zip(function_rows, function_ast_nodes):
        fn_doc = ast.get_docstring(func_node)
        fn_src = ast.get_source_segment(source_code, func_node) or ""
        ops_cc.extend(
            _code_content_insert_ops(
                file_id=file_id,
                entity_type="function",
                entity_id=row["id"],
                entity_name=str(row.get("name") or getattr(func_node, "name", "")),
                content=fn_src,
                docstring=fn_doc,
                driver_type=driver_type,
            )
        )
    if ops_cc:
        batches.append(ops_cc)

    # Reindex-success clear: this batch performs a full atomic reindex of the file
    # (classes/methods/functions/imports/code_content), so any content_stale flag
    # set by the write that triggered it (bug 56c23bd9) is resolved in the same
    # transaction (defense-in-depth: compose_cst_writer.apply_changes /
    # restore_backup_file both route through this function).
    from ..sql_portable import sql_julian_timestamp_now_expr

    _now_clear = sql_julian_timestamp_now_expr(None)
    batches.append(
        [
            (
                f"UPDATE files SET content_stale = 0, content_stale_since = NULL, "
                f"updated_at = {_now_clear} WHERE id = ?",
                (file_id,),
            )
        ]
    )

    meta: dict[str, Any] = {
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
    return (batches, meta)


def update_file_data_atomic_batch(
    database: Any,
    file_id: str,
    project_id: str,
    source_code: str,
    file_path: str,
    file_mtime: float,
    transaction_id: Optional[str] = None,
    *,
    skip_file_edit_lock: bool = False,
) -> Dict[str, Any]:
    """
    Update all file data (AST, CST, classes, methods, functions, imports).

    When ``transaction_id`` is set and ``skip_file_edit_lock`` is True, the caller
    already opened a transaction and acquired ``files.editing_pid`` on that same
    connection; this function only runs the batch SQL on ``transaction_id`` (no
    nested ``execute_logical_write_operation`` transaction).

    Otherwise this function begins a transaction, optionally acquires the edit
    lock on that connection, runs batches, clears ``editing_pid`` on the same
    connection, then commits (avoids a second pool connection after commit).
    """
    logger.info(
        "update_file_data_atomic_batch file_id=%s (logical write)",
        file_id,
    )
    from code_analysis.core.database.file_edit_lock import (
        acquire_file_edit_lock_with_retry,
        release_file_edit_lock,
    )

    batches, meta = build_file_data_atomic_batches(
        file_id,
        project_id,
        source_code,
        file_path,
        file_mtime,
        driver_type=getattr(database, "_driver_type", None),
    )
    if meta.get("success") is False:
        return meta
    if not batches:
        raise RuntimeError(
            "build_file_data_atomic_batches returned empty batches with success=True",
        )

    if transaction_id is not None and skip_file_edit_lock:
        err = execute_all_batches_in_transaction(
            database,
            batches,
            transaction_id,
            file_path=file_path,
            file_id=file_id,
        )
        if err is not None:
            return err
        return {**meta, "success": True}

    lock_held = False
    try:
        if not skip_file_edit_lock:
            if not acquire_file_edit_lock_with_retry(
                database, file_id, transaction_id=None
            ):
                return {
                    "success": False,
                    "error": (
                        "File is being edited by another live process (file edit lock). "
                        "Try again shortly."
                    ),
                    "error_code": "FILE_EDIT_LOCKED",
                    "file_path": file_path,
                    "file_id": file_id,
                }
            lock_held = True

        try:
            submit_logical_write_or_fallback(database, batches)
        except Exception as e:
            logger.exception("logical write failed for %s", file_path)
            return {
                "success": False,
                "error": str(e),
                "file_path": file_path,
                "file_id": file_id,
            }
    finally:
        if lock_held:
            try:
                release_file_edit_lock(database, file_id, transaction_id=None)
            except Exception:
                logger.warning(
                    "release_file_edit_lock failed for file_id=%s",
                    file_id,
                    exc_info=True,
                )

    return {**meta, "success": True}
