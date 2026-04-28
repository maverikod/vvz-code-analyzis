"""
Read API for file tree snapshot structure (node_id, parent_node_id, child_index).

Exposes the latest snapshot tree for a file so clients can reconstruct parent-child
and sibling order. node_id is UUID4 and matches entity cst_node_id and in-memory
tree node_id (file_tree_snapshot_nodes.node_id = entity cst_node_id).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def get_snapshot_tree_structure(
    project_id: str,
    file_path: str,
    database: Any,
) -> Dict[str, Any]:
    """
    Return snapshot tree structure for a file: nodes with node_id, parent_node_id, child_index.

    Resolves file_id from project_id + file_path, loads the latest file_tree_snapshot
    for that file, and returns snapshot metadata plus a list of nodes. node_id is UUID4
    and matches entity cst_node_id and in-memory tree node_id; clients can use this to
    build real trees (parent-child, sibling order) and correlate with relationship commands.

    Args:
        project_id: Project UUID.
        file_path: File path (relative to project root or absolute; resolved via project root).
        database: CodeDatabase-like instance with get_project, get_file_by_path, _fetchone, _fetchall.

    Returns:
        Dict with:
            has_snapshot: True if a snapshot exists for the file, False otherwise.
            snapshot_id: Snapshot id (int) or None when no snapshot.
            root_node_id: Root node UUID4 or None when no snapshot.
            nodes: List of {"node_id", "parent_node_id", "child_index"} dicts, ordered by
                   parent_node_id, child_index. Empty when no snapshot.
    """
    result: Dict[str, Any] = {
        "has_snapshot": False,
        "snapshot_id": None,
        "root_node_id": None,
        "nodes": [],
    }

    project = database.get_project(project_id)
    if not project:
        return result

    root_path = project.get("root_path")
    if not root_path:
        return result

    abs_path = str((Path(root_path) / file_path).resolve())
    file_record = database.get_file_by_path(abs_path, project_id)
    if not file_record:
        return result

    file_id = file_record["id"]
    snapshot_row = database._fetchone(
        "SELECT id FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1",
        (file_id,),
    )
    if not snapshot_row:
        return result

    snapshot_id = str(snapshot_row["id"])
    result["snapshot_id"] = snapshot_id
    result["has_snapshot"] = True

    root_row = database._fetchone(
        "SELECT root_node_id FROM file_tree_snapshot_roots WHERE snapshot_id = ?",
        (snapshot_id,),
    )
    if root_row:
        result["root_node_id"] = root_row["root_node_id"]

    node_rows = database._fetchall(
        """
        SELECT node_id, parent_node_id, child_index
        FROM file_tree_snapshot_nodes
        WHERE snapshot_id = ?
        ORDER BY parent_node_id, child_index
        """,
        (snapshot_id,),
    )
    result["nodes"] = [
        {
            "node_id": r["node_id"],
            "parent_node_id": r["parent_node_id"],
            "child_index": int(r["child_index"]),
        }
        for r in (node_rows or [])
    ]
    return result
