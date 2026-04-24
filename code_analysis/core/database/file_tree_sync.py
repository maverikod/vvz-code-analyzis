"""
Unified file-level sync service: one coordinated DB write per file.

Writes all file-level structures (snapshot, root, nodes, AST, CST, entities)
via one logical write RPC. Used by tree-save and background-indexing flows.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from ..database_client.file_data_batch import build_file_data_atomic_batches

logger = logging.getLogger(__name__)

# Multi-row INSERT chunk size for file_tree_snapshot_nodes. Each row binds four
# placeholders (file_id for snapshot subquery, node_id, parent_node_id, child_index).
# Stay below SQLite's SQLITE_MAX_VARIABLE_NUMBER (often 999) with margin.
FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE = 200


def _build_snapshot_node_insert_ops(
    file_id: int,
    node_rows: List[Tuple[str, Optional[str], int]],
    *,
    chunk_size: Optional[int] = None,
) -> List[Tuple[str, Any]]:
    """
    Build one or more INSERT statements with multiple VALUES rows each.

    Replaces N single-row INSERT ops with ceil(N/chunk_size) multi-row ops to
    shrink logical-write RPC payload (same DB effect as row-by-row inserts).
    """
    if not node_rows:
        return []
    size = (
        chunk_size
        if chunk_size is not None
        else FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE
    )
    if size < 1:
        raise ValueError("chunk_size must be >= 1")
    ops: List[Tuple[str, Any]] = []
    row_fragment = (
        "((SELECT id FROM file_tree_snapshots WHERE file_id = ? "
        "ORDER BY id DESC LIMIT 1), ?, ?, ?)"
    )
    for i in range(0, len(node_rows), size):
        chunk = node_rows[i : i + size]
        values_sql = ",\n".join(row_fragment for _ in chunk)
        sql = (
            "INSERT INTO file_tree_snapshot_nodes "
            "(snapshot_id, node_id, parent_node_id, child_index) VALUES\n" + values_sql
        )
        params: List[Any] = []
        for nid, pid, cidx in chunk:
            params.extend((file_id, nid, pid, cidx))
        ops.append((sql, tuple(params)))
    return ops


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
        database: CodeDatabase-like instance with get_file_by_path and
            execute_logical_write_operation (one composite RPC on SQLite client).
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

    t0 = time.perf_counter()
    logger.info(
        "[SAVE_PATH] sync_file_to_db_atomic enter project_id=%s file_id=%s path=%s",
        project_id,
        file_id,
        absolute_path,
    )

    def _sync() -> Dict[str, Any]:
        nonlocal file_id
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

        fd_batches, meta = build_file_data_atomic_batches(
            file_id,
            project_id,
            source_code,
            absolute_path,
            file_mtime,
        )
        if meta.get("success") is False:
            result["error"] = meta.get("error", "AST parse failed")
            return result

        root_node_id = tree.root_node_id
        if not root_node_id:
            result["error"] = "CST tree has no root node"
            return result

        node_rows = _build_snapshot_node_rows(tree, 0)

        # Child-first teardown: do not rely on ON DELETE CASCADE on legacy/migrated DBs.
        s_batches: list[list[Tuple[str, Any]]] = [
            [
                (
                    "DELETE FROM file_tree_snapshot_nodes WHERE snapshot_id IN ("
                    "SELECT id FROM file_tree_snapshots WHERE file_id = ?)",
                    (file_id,),
                ),
                (
                    "DELETE FROM file_tree_snapshot_roots WHERE snapshot_id IN ("
                    "SELECT id FROM file_tree_snapshots WHERE file_id = ?)",
                    (file_id,),
                ),
                (
                    "DELETE FROM file_tree_snapshots WHERE file_id = ?",
                    (file_id,),
                ),
            ],
            [
                (
                    "INSERT INTO file_tree_snapshots "
                    "(file_id, project_id, source_payload, file_mtime) "
                    "VALUES (?, ?, ?, ?)",
                    (file_id, project_id, source_code, file_mtime),
                )
            ],
            [
                (
                    "INSERT INTO file_tree_snapshot_roots (snapshot_id, root_node_id) "
                    "VALUES ("
                    "(SELECT id FROM file_tree_snapshots WHERE file_id = ? "
                    "ORDER BY id DESC LIMIT 1), ?)",
                    (file_id, root_node_id),
                )
            ],
        ]

        if node_rows:
            node_ops = _build_snapshot_node_insert_ops(file_id, node_rows)
            s_batches.append(node_ops)

        all_batches = s_batches + fd_batches
        if not all_batches:
            result["error"] = "No SQL batches to execute"
            return result

        try:
            raw = database.execute_logical_write_operation({"batches": all_batches})
        except Exception as e:
            logger.exception("sync_file_to_db_atomic failed for %s", absolute_path)
            result["error"] = str(e)
            return result

        if not (isinstance(raw, dict) and raw.get("success")):
            result["error"] = "Logical write did not report success"
            return result

        result["success"] = True
        result["snapshot"] = 1
        result["roots"] = 1
        result["nodes"] = len(node_rows)
        result["ast_updated"] = meta.get("ast_updated", False)
        result["cst_updated"] = meta.get("cst_updated", False)
        result["entities_updated"] = meta.get("entities_updated", 0)
        return result

    try:
        return _sync()
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "[SAVE_PATH] sync_file_to_db_atomic exit project_id=%s file_id=%s elapsed_ms=%.1f success=%s",
            project_id,
            result.get("file_id"),
            elapsed_ms,
            result.get("success"),
        )


def _build_snapshot_node_rows(
    tree: Any,
    snapshot_id: int,
) -> List[Tuple[str, Optional[str], int]]:
    """
    Build (node_id, parent_node_id, child_index) for all nodes in the tree.

    Root has parent_node_id=None and child_index=0. Other nodes use their
    parent's children_ids order for child_index. snapshot_id is unused;
    caller binds snapshot via SQL subquery.
    """
    _ = snapshot_id
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
