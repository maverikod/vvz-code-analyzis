"""
Database backup, delete, and restore for compose_cst_module.

Used by ComposeCSTModuleCommand and compose_cst_writer for transactional file updates.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _extract_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract row list from execute/execute_batch result."""
    if isinstance(result, dict):
        data = result.get("data", [])
        return data if isinstance(data, list) else []
    return []


def backup_file_data(database: Any, file_id: int) -> Optional[Dict[str, Any]]:
    """
    Backup all file data from database using batch RPC.

    Args:
        database: Database instance
        file_id: File ID

    Returns:
        Dictionary with backed up data or None if file not found
    """
    t0 = time.perf_counter()

    backup_ops = [
        ("SELECT * FROM files WHERE id = ?", (file_id,)),
        ("SELECT * FROM classes WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM functions WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM imports WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM usages WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM issues WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM code_content WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM ast_trees WHERE file_id = ?", (file_id,)),
        ("SELECT * FROM cst_trees WHERE file_id = ?", (file_id,)),
    ]
    results = database.execute_batch(backup_ops)
    if len(results) < 9:
        return None
    file_rows = _extract_rows(results[0])
    if not file_rows:
        return None
    file_record = file_rows[0]

    backup_data: Dict[str, Any] = {
        "file_record": file_record,
        "classes": _extract_rows(results[1]),
        "functions": _extract_rows(results[2]),
        "imports": _extract_rows(results[3]),
        "usages": _extract_rows(results[4]),
        "issues": _extract_rows(results[5]),
        "code_content": _extract_rows(results[6]),
        "ast_trees": _extract_rows(results[7]),
        "cst_trees": _extract_rows(results[8]),
    }

    class_ids = [row["id"] for row in backup_data["classes"]]
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        methods_results = database.execute_batch(
            [
                (
                    f"SELECT * FROM methods WHERE class_id IN ({placeholders})",
                    tuple(class_ids),
                )
            ]
        )
        backup_data["methods"] = (
            _extract_rows(methods_results[0]) if methods_results else []
        )
    else:
        backup_data["methods"] = []

    logger.info(
        "[PROFILE] _backup_file_data file_id=%s elapsed=%.3fs",
        file_id,
        time.perf_counter() - t0,
    )
    return backup_data


def delete_file_data(
    database: Any,
    file_id: int,
    transaction_id: Optional[str] = None,
) -> None:
    """
    Delete all file data within transaction using batch RPC.

    Args:
        database: Database instance
        file_id: File ID
        transaction_id: Optional transaction ID (must be set when inside a transaction)
    """
    t0 = time.perf_counter()

    select_ops = [
        ("SELECT id FROM classes WHERE file_id = ?", (file_id,)),
        ("SELECT id FROM code_content WHERE file_id = ?", (file_id,)),
    ]
    select_results = database.execute_batch(select_ops, transaction_id)
    if len(select_results) < 2:
        logger.warning("_delete_file_data: execute_batch returned < 2 results")
        return
    class_data = (
        select_results[0].get("data", []) if isinstance(select_results[0], dict) else []
    )
    content_data = (
        select_results[1].get("data", []) if isinstance(select_results[1], dict) else []
    )
    class_ids = [row["id"] for row in class_data]
    content_ids = [row["id"] for row in content_data]

    delete_ops: List[tuple] = []
    if content_ids:
        placeholders = ",".join("?" * len(content_ids))
        delete_ops.append(
            (
                f"DELETE FROM code_content_fts WHERE rowid IN ({placeholders})",
                tuple(content_ids),
            )
        )
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        delete_ops.append(
            (
                f"DELETE FROM methods WHERE class_id IN ({placeholders})",
                tuple(class_ids),
            )
        )
    delete_ops.extend(
        [
            ("DELETE FROM classes WHERE file_id = ?", (file_id,)),
            ("DELETE FROM functions WHERE file_id = ?", (file_id,)),
            ("DELETE FROM imports WHERE file_id = ?", (file_id,)),
            ("DELETE FROM issues WHERE file_id = ?", (file_id,)),
            ("DELETE FROM usages WHERE file_id = ?", (file_id,)),
            ("DELETE FROM code_content WHERE file_id = ?", (file_id,)),
            ("DELETE FROM ast_trees WHERE file_id = ?", (file_id,)),
            ("DELETE FROM cst_trees WHERE file_id = ?", (file_id,)),
            ("DELETE FROM code_chunks WHERE file_id = ?", (file_id,)),
            (
                "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
                (file_id,),
            ),
        ]
    )
    if class_ids:
        placeholders = ",".join("?" * len(class_ids))
        delete_ops.append(
            (
                """
                DELETE FROM vector_index
                WHERE entity_type IN ('class', 'function', 'method')
                AND entity_id IN ({})
                """.format(
                    placeholders
                ),
                tuple(class_ids),
            )
        )
    database.execute_batch(delete_ops, transaction_id)
    logger.info(
        "[PROFILE] _delete_file_data file_id=%s elapsed=%.3fs",
        file_id,
        time.perf_counter() - t0,
    )


def _restore_entities(database: Any, backup_data: Dict[str, Any]) -> None:
    """Restore entities (classes, methods, functions) from backup."""
    for row in backup_data["classes"]:
        line_val = row.get("start_line", row.get("line", 0))
        database.execute(
            """
            INSERT OR REPLACE INTO classes (id, file_id, name, line, end_line, docstring, bases)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["name"],
                line_val,
                row.get("end_line"),
                row.get("docstring"),
                row.get("bases"),
            ),
        )

    for row in backup_data["methods"]:
        line_val = row.get("start_line", row.get("line", 0))
        args_val = row.get("parameters", row.get("args"))
        database.execute(
            """
            INSERT OR REPLACE INTO methods (id, class_id, name, line, end_line, args, docstring,
                is_abstract, has_pass, has_not_implemented, complexity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["class_id"],
                row["name"],
                line_val,
                row.get("end_line"),
                args_val,
                row.get("docstring"),
                row.get("is_abstract", 0),
                row.get("has_pass", 0),
                row.get("has_not_implemented", 0),
                row.get("complexity"),
            ),
        )

    for row in backup_data["functions"]:
        line_val = row.get("start_line", row.get("line", 0))
        args_val = row.get("parameters", row.get("args"))
        database.execute(
            """
            INSERT OR REPLACE INTO functions (id, file_id, name, line, end_line, args, docstring, complexity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["name"],
                line_val,
                row.get("end_line"),
                args_val,
                row.get("docstring"),
                row.get("complexity"),
            ),
        )


def _restore_metadata(database: Any, backup_data: Dict[str, Any]) -> None:
    """Restore metadata (imports, usages, issues, content) from backup."""
    for row in backup_data["imports"]:
        database.execute(
            """
            INSERT OR REPLACE INTO imports (id, file_id, module, name, alias, import_type, line)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["module"],
                row["name"],
                row.get("alias"),
                row["import_type"],
                row["line"],
            ),
        )

    for row in backup_data["usages"]:
        database.execute(
            """
            INSERT OR REPLACE INTO usages (id, file_id, entity_type, entity_name, line, column)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["entity_type"],
                row["entity_name"],
                row["line"],
                row.get("column"),
            ),
        )

    for row in backup_data["issues"]:
        database.execute(
            """
            INSERT OR REPLACE INTO issues (id, file_id, issue_type, message, line, column)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["issue_type"],
                row["message"],
                row["line"],
                row.get("column"),
            ),
        )

    for row in backup_data["code_content"]:
        database.execute(
            """
            INSERT OR REPLACE INTO code_content (id, file_id, content, start_line, end_line)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["content"],
                row["start_line"],
                row["end_line"],
            ),
        )


def _restore_trees(database: Any, backup_data: Dict[str, Any]) -> None:
    """Restore AST and CST trees from backup."""
    for row in backup_data["ast_trees"]:
        database.execute(
            """
            INSERT OR REPLACE INTO ast_trees (id, file_id, project_id, ast_json, ast_hash, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["project_id"],
                row["ast_json"],
                row["ast_hash"],
                row["file_mtime"],
            ),
        )

    for row in backup_data["cst_trees"]:
        database.execute(
            """
            INSERT OR REPLACE INTO cst_trees (id, file_id, project_id, cst_code, cst_hash, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["file_id"],
                row["project_id"],
                row["cst_code"],
                row["cst_hash"],
                row["file_mtime"],
            ),
        )


def restore_file_data(database: Any, file_id: int, backup_data: Dict[str, Any]) -> None:
    """
    Restore file data from backup.

    Args:
        database: Database instance
        file_id: File ID
        backup_data: Backed up data
    """
    file_record = backup_data["file_record"]
    database.execute(
        """
        UPDATE files SET
            path = ?, lines = ?, last_modified = ?, has_docstring = ?,
            project_id = ?, updated_at = julianday('now')
        WHERE id = ?
        """,
        (
            file_record["path"],
            file_record["lines"],
            file_record["last_modified"],
            file_record["has_docstring"],
            file_record["project_id"],
            file_id,
        ),
    )

    _restore_entities(database, backup_data)
    _restore_metadata(database, backup_data)
    _restore_trees(database, backup_data)
