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
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from ..database_client.file_data_batch import (
    build_file_data_atomic_batches,
    execute_all_batches_in_transaction,
)

logger = logging.getLogger(__name__)

# Multi-row INSERT chunk size for file_tree_snapshot_nodes. Each row binds five
# placeholders (node row id, snapshot_id, node_id, parent_node_id, child_index).
# Stay below SQLite's SQLITE_MAX_VARIABLE_NUMBER (often 999) with margin.
FILE_TREE_SNAPSHOT_NODES_INSERT_CHUNK_SIZE = 200


def _build_snapshot_node_insert_ops(
    snapshot_id: str,
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
    row_fragment = "(?, ?, ?, ?, ?)"
    for i in range(0, len(node_rows), size):
        chunk = node_rows[i : i + size]
        values_sql = ",\n".join(row_fragment for _ in chunk)
        sql = (
            "INSERT INTO file_tree_snapshot_nodes "
            "(id, snapshot_id, node_id, parent_node_id, child_index) VALUES\n"
            + values_sql
        )
        params: List[Any] = []
        for nid, pid, cidx in chunk:
            params.extend(
                (str(uuid.uuid4()), snapshot_id, nid, pid, cidx),
            )
        ops.append((sql, tuple(params)))
    return ops


def sync_file_to_db_atomic(
    database: Any,
    project_id: str,
    absolute_path: str,
    source_code: str,
    file_mtime: float,
    file_id: Optional[str] = None,
    *,
    skip_file_edit_lock: bool = False,
    prebuilt_cst_tree: Any = None,
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
        file_id: Optional existing file row id (UUID string or legacy int);
            if None, resolved by path and project_id.
        skip_file_edit_lock: When True, do not take ``files.editing_pid`` (caller holds it).
        prebuilt_cst_tree: Optional in-memory :class:`~code_analysis.core.cst_tree.models.CSTTree`
            aligned with ``source_code``. When set, skips ``create_tree_from_code`` entirely so DB
            snapshot node IDs match the caller's tree (e.g. ``cst_save_tree`` / combined
            ``cst_modify_tree`` with clean ``.py`` and sidecar identities). Callers that pass this
            **must** persist ``.cst`` sidecar themselves when applicable (e.g.
            ``save_tree_to_file`` → ``write_sidecar_atomic`` after sync). This function must not
            call ``create_tree_from_code(..., persist_sidecar=True)`` in that mode: a fresh parse
            would assign new UUIDs and could overwrite the sidecar on disk before the caller
            writes the authoritative tree.

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
        from code_analysis.core.database.file_edit_lock import (
            acquire_file_edit_lock_with_retry,
            release_file_edit_lock,
        )

        if file_id is None:
            file_record = database.get_file_by_path(absolute_path, project_id)
            if not file_record:
                result["error"] = f"File not found in database: {absolute_path}"
                return result
            file_id = str(file_record["id"])
        result["file_id"] = file_id

        lock_held = False
        own_tid: Optional[str] = None
        try:
            from ..cst_tree.tree_builder import create_tree_from_code
        except Exception as e:
            logger.exception("Failed to import create_tree_from_code")
            result["error"] = f"Failed to build CST: {e}"
            return result

        try:
            if prebuilt_cst_tree is not None:
                # Do not parse or persist sidecar here; caller owns sidecar after DB sync.
                tree = prebuilt_cst_tree
            else:
                # Indexer / repair: build CST from ``source_code``; may write sidecar when enabled.
                tree = create_tree_from_code(
                    absolute_path,
                    source_code,
                    persist_sidecar=True,
                    register_in_memory=False,
                )
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
            driver_type=getattr(database, "_driver_type", None),
        )
        if meta.get("success") is False:
            result["error"] = meta.get("error", "AST parse failed")
            return result

        root_node_id = tree.root_node_id
        if not root_node_id:
            result["error"] = "CST tree has no root node"
            return result

        node_rows = _build_snapshot_node_rows(tree, 0)

        snapshot_row_id = str(uuid.uuid4())

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
                    "(id, file_id, project_id, source_payload, file_mtime) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (snapshot_row_id, file_id, project_id, source_code, file_mtime),
                )
            ],
            [
                (
                    "INSERT INTO file_tree_snapshot_roots (snapshot_id, root_node_id) "
                    "VALUES (?, ?)",
                    (snapshot_row_id, root_node_id),
                )
            ],
        ]

        if node_rows:
            node_ops = _build_snapshot_node_insert_ops(snapshot_row_id, node_rows)
            s_batches.append(node_ops)

        all_batches = s_batches + fd_batches
        if not all_batches:
            result["error"] = "No SQL batches to execute"
            return result

        own_tid = database.begin_transaction()
        if not own_tid:
            result["error"] = "Database transaction could not be started"
            result["error_code"] = "TRANSACTION_ERROR"
            return result

        if not skip_file_edit_lock:
            if not acquire_file_edit_lock_with_retry(
                database, file_id, transaction_id=own_tid
            ):
                try:
                    database.rollback_transaction(own_tid)
                except Exception:
                    pass
                own_tid = None
                result["error"] = (
                    "File is being edited by another live process (file edit lock). "
                    "Try again shortly."
                )
                result["error_code"] = "FILE_EDIT_LOCKED"
                return result
            lock_held = True

        batch_err = execute_all_batches_in_transaction(
            database,
            all_batches,
            own_tid,
            file_path=str(absolute_path),
            file_id=file_id,
        )
        if batch_err is not None:
            try:
                database.rollback_transaction(own_tid)
            except Exception:
                pass
            own_tid = None
            result["error"] = batch_err.get("error", "batch failed")
            return result

        if lock_held:
            release_file_edit_lock(database, file_id, transaction_id=own_tid)
        database.commit_transaction(own_tid)
        own_tid = None
        lock_held = False

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

    ``child_index`` values under the same ``parent_node_id`` must be unique:
    ``file_tree_snapshot_nodes`` has a unique constraint on
    (snapshot_id, parent_node_id, child_index). Nodes missing from the
    parent's ``children_ids`` (stale metadata after reindex, etc.) used to
    all fall back to index 0 and caused duplicate-key failures; those
    children are appended after the ordered slice with monotonic indices.
    """
    _ = snapshot_id
    metadata_map = getattr(tree, "metadata_map", {})
    parent_map = getattr(tree, "parent_map", {})

    by_parent: Dict[Optional[str], List[str]] = defaultdict(list)
    for node_id in metadata_map:
        by_parent[parent_map.get(node_id)].append(node_id)

    rows: List[Tuple[str, Optional[str], int]] = []
    for parent_node_id, child_node_ids in by_parent.items():
        if parent_node_id is None:
            for idx, node_id in enumerate(sorted(child_node_ids)):
                rows.append((node_id, None, idx))
            continue

        parent_meta = metadata_map.get(parent_node_id)
        preferred_order = list(
            getattr(parent_meta, "children_ids", []) or [],
        )

        assigned: Dict[str, int] = {}
        next_idx = 0
        for cid in preferred_order:
            if cid in child_node_ids and cid not in assigned:
                assigned[cid] = next_idx
                next_idx += 1

        for nid in sorted(child_node_ids):
            if nid not in assigned:
                logger.warning(
                    "Snapshot row: node %s has parent %s but is not listed in "
                    "that parent's children_ids; assigning child_index=%s",
                    nid,
                    parent_node_id,
                    next_idx,
                )
                assigned[nid] = next_idx
                next_idx += 1

        for node_id in child_node_ids:
            rows.append((node_id, parent_node_id, assigned[node_id]))
    return rows
