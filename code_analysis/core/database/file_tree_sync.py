"""
Unified file-level sync service: one coordinated DB write per file.

Writes all file-level structures (snapshot, root, nodes, AST, CST, entities)
in a single transaction. Used by tree-save and background-indexing flows.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def sync_file_to_db_atomic(
    database: Any,
    project_id: str,
    absolute_path: str,
    source_code: str,
    file_mtime: float,
    file_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Rebuild and write all file-level DB structures for one file in one coordinated operation.

    Input is file-centric: project_id, absolute file path, source code, mtime.
    Ensures file-level atomicity: either the file is fully written or the operation
    fails (no partial success). Used by both tree-save and background-indexing callers.

    Args:
        database: CodeDatabase-like instance with get_file_by_path, execute_batch,
            begin_transaction, commit_transaction, rollback_transaction.
        project_id: Project ID.
        absolute_path: Absolute normalized file path.
        source_code: Full source code of the file.
        file_mtime: File mtime (Unix timestamp) for operational metadata.
        file_id: Optional existing file_id; if None, resolved by path and project_id.

    Returns:
        Dict with:
            success: True if the entire file sync completed.
            file_id: Resolved or provided file_id (None on failure before resolve).
            snapshot: Number of snapshot rows written (0 or 1).
            roots: Number of root rows written (0 or 1).
            nodes: Number of node rows written.
            ast_updated: True if AST was written.
            cst_updated: True if CST was written.
            entities_updated: Count of entities (classes, functions, methods, imports).
            error: Error message when success is False.
    """
    result: Dict[str, Any] = {
        "success": False,
        "file_id": None,
        "snapshot": 0,
        "roots": 0,
        "nodes": 0,
        "ast_updated": False,
        "cst_updated": False,
        "entities_updated": 0,
        "error": None,
    }

    if file_id is None:
        file_record = database.get_file_by_path(absolute_path, project_id)
        if not file_record:
            result["error"] = f"File not found in database: {absolute_path}"
            return result
        file_id = file_record["id"]
    result["file_id"] = file_id

    try:
        from ..cst_tree.tree_builder import create_tree_from_code
    except Exception as e:
        logger.exception("Failed to import create_tree_from_code")
        result["error"] = f"Failed to build CST: {e}"
        return result

    try:
        tree = create_tree_from_code(absolute_path, source_code)
    except Exception as e:
        logger.warning("CST build failed for %s: %s", absolute_path, e)
        result["error"] = f"Failed to build CST: {e}"
        return result

    transaction_id: Optional[str] = None
    try:
        transaction_id = database.begin_transaction()
    except RuntimeError as e:
        result["error"] = str(e)
        return result

    try:
        # Clear existing snapshot data for this file (CASCADE removes roots and nodes).
        database.execute_batch(
            [
                (
                    "DELETE FROM file_tree_snapshots WHERE file_id = ?",
                    (file_id,),
                )
            ],
            transaction_id,
        )

        # Insert snapshot and get snapshot_id.
        ins_snapshot_sql = (
            "INSERT INTO file_tree_snapshots "
            "(file_id, project_id, source_payload, file_mtime) VALUES (?, ?, ?, ?)"
        )
        ins_snapshot_params = (file_id, project_id, source_code, file_mtime)
        snapshot_results = database.execute_batch(
            [(ins_snapshot_sql, ins_snapshot_params)],
            transaction_id,
        )
        if not snapshot_results:
            result["error"] = "Snapshot insert returned no result"
            database.rollback_transaction(transaction_id)
            return result
        snapshot_id = snapshot_results[0].get("lastrowid")
        if snapshot_id is None:
            result["error"] = "Snapshot insert did not return lastrowid"
            database.rollback_transaction(transaction_id)
            return result
        snapshot_id = int(snapshot_id)
        result["snapshot"] = 1

        root_node_id = tree.root_node_id
        if not root_node_id:
            result["error"] = "CST tree has no root node"
            database.rollback_transaction(transaction_id)
            return result

        database.execute_batch(
            [
                (
                    "INSERT INTO file_tree_snapshot_roots (snapshot_id, root_node_id) VALUES (?, ?)",
                    (snapshot_id, root_node_id),
                )
            ],
            transaction_id,
        )
        result["roots"] = 1

        node_rows = _build_snapshot_node_rows(tree, snapshot_id)
        if node_rows:
            node_ops: List[Tuple[str, Tuple[Any, ...]]] = [
                (
                    "INSERT INTO file_tree_snapshot_nodes "
                    "(snapshot_id, node_id, parent_node_id, child_index) VALUES (?, ?, ?, ?)",
                    (snapshot_id, nid, pid, cidx),
                )
                for (nid, pid, cidx) in node_rows
            ]
            database.execute_batch(node_ops, transaction_id)
        result["nodes"] = len(node_rows)

        from ..database_client.file_data_batch import update_file_data_atomic_batch

        batch_result = update_file_data_atomic_batch(
            database,
            file_id,
            project_id,
            source_code,
            absolute_path,
            file_mtime,
            transaction_id=transaction_id,
        )
        if not batch_result.get("success"):
            result["error"] = batch_result.get("error", "Batch update failed")
            database.rollback_transaction(transaction_id)
            return result

        result["ast_updated"] = batch_result.get("ast_updated", False)
        result["cst_updated"] = batch_result.get("cst_updated", False)
        result["entities_updated"] = batch_result.get("entities_updated", 0)
        database.commit_transaction(transaction_id)
        result["success"] = True
        return result

    except Exception as e:
        logger.exception("sync_file_to_db_atomic failed for %s", absolute_path)
        result["error"] = str(e)
        if transaction_id is not None:
            try:
                database.rollback_transaction(transaction_id)
            except Exception:
                pass
        return result


def _build_snapshot_node_rows(
    tree: Any,
    snapshot_id: int,
) -> List[Tuple[str, Optional[str], int]]:
    """
    Build (node_id, parent_node_id, child_index) for all nodes in the tree.

    Root has parent_node_id=None and child_index=0. Other nodes use their
    parent's children_ids order for child_index. snapshot_id is not used in
    the tuple; caller binds it when inserting.
    """
    rows: List[Tuple[str, Optional[str], int]] = []
    metadata_map = getattr(tree, "metadata_map", {})
    parent_map = getattr(tree, "parent_map", {})

    for node_id in metadata_map:
        parent_node_id = parent_map.get(node_id)
        if parent_node_id is None:
            child_index = 0
        else:
            parent_meta = metadata_map.get(parent_node_id)
            children_ids = list(getattr(parent_meta, "children_ids", []) or [])
            child_index = next(
                (i for i, cid in enumerate(children_ids) if cid == node_id),
                0,
            )
        rows.append((node_id, parent_node_id, child_index))
    return rows
