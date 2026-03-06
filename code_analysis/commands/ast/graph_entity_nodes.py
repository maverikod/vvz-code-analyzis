"""
Build entity_nodes payloads for export_graph (file_path + cst_node_id per entity).

Contract: All entity nodes returned by this module for relationship/graph use MUST
include "file_path" and "cst_node_id" (valid UUID4). The cst_node_id is the same
identifier as file_tree_snapshot_nodes.node_id, so clients can correlate entities
with snapshot tree nodes. No code path in this module returns an entity without
valid cst_node_id; relationship commands are the read-side counterpart to snapshot
node identity.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Callable, Dict, List, Set


def build_entity_nodes_hierarchy(
    rows: List[Any],
    is_valid_uuid4: Callable[[Any], bool],
) -> List[Dict[str, str]]:
    """Build entity_nodes from hierarchy query rows (classes with file_path, cst_node_id).

    Only includes entries with valid UUID4 cst_node_id and non-empty file_path.
    Aligns with snapshot node identity: cst_node_id equals file_tree_snapshot_nodes.node_id.

    Args:
        rows: Rows from SELECT c.name, c.bases, f.path, c.cst_node_id ...
        is_valid_uuid4: Predicate for valid UUID4 string.

    Returns:
        List of {"node_id", "file_path", "cst_node_id"} dicts; all have valid UUID4.
    """
    out: List[Dict[str, str]] = []
    for r in rows:
        name = r.get("name") if hasattr(r, "get") else r.get("name")
        file_path_val = r.get("file_path") if hasattr(r, "get") else r.get("file_path")
        cid = r.get("cst_node_id") if hasattr(r, "get") else r.get("cst_node_id")
        if not name:
            continue
        node_id_str = str(name)
        if not is_valid_uuid4(cid) or not file_path_val:
            continue
        out.append(
            {
                "node_id": node_id_str,
                "file_path": str(file_path_val),
                "cst_node_id": str(cid).strip(),
            }
        )
    return out


def build_entity_nodes_call_graph(
    db: Any,
    project_id: str,
    to_node_ids: Set[str],
    is_valid_uuid4: Callable[[Any], bool],
) -> List[Dict[str, str]]:
    """Resolve call_graph 'to' node ids to entities with file_path and cst_node_id.

    Queries classes, functions, methods with valid cst_node_id and appends
    matching entity payloads. Only includes entries with valid UUID4.
    cst_node_id aligns with file_tree_snapshot_nodes.node_id for tree correlation.

    Args:
        db: Database driver with execute() returning {"data": list of rows}.
        project_id: Project UUID.
        to_node_ids: Set of destination node id strings (e.g. "Class.method" or "func").
        is_valid_uuid4: Predicate for valid UUID4 string.

    Returns:
        List of {"node_id", "file_path", "cst_node_id"} dicts; all have valid UUID4.
    """
    out: List[Dict[str, str]] = []
    classes_res = db.execute(
        """
        SELECT c.name, f.path AS file_path, c.cst_node_id
        FROM classes c
        JOIN files f ON f.id = c.file_id
        WHERE f.project_id = ? AND c.cst_node_id IS NOT NULL
        AND c.cst_node_id != ''
        """,
        (project_id,),
    )
    funcs_res = db.execute(
        """
        SELECT func.name, f.path AS file_path, func.cst_node_id
        FROM functions func
        JOIN files f ON f.id = func.file_id
        WHERE f.project_id = ? AND func.cst_node_id IS NOT NULL
        AND func.cst_node_id != ''
        """,
        (project_id,),
    )
    methods_res = db.execute(
        """
        SELECT m.name AS method_name, c.name AS class_name,
               f.path AS file_path, m.cst_node_id
        FROM methods m
        JOIN classes c ON c.id = m.class_id
        JOIN files f ON f.id = c.file_id
        WHERE f.project_id = ? AND m.cst_node_id IS NOT NULL
        AND m.cst_node_id != ''
        """,
        (project_id,),
    )
    for row in classes_res.get("data", []) or []:
        name_val = row.get("name") or row["name"]
        node_id_str = str(name_val)
        if node_id_str not in to_node_ids:
            continue
        cid = row.get("cst_node_id")
        fpath = row.get("file_path")
        if is_valid_uuid4(cid) and fpath:
            out.append(
                {
                    "node_id": node_id_str,
                    "file_path": str(fpath),
                    "cst_node_id": str(cid).strip(),
                }
            )
    for row in funcs_res.get("data", []) or []:
        name_val = row.get("name") or row["name"]
        node_id_str = str(name_val)
        if node_id_str not in to_node_ids:
            continue
        cid = row.get("cst_node_id")
        fpath = row.get("file_path")
        if is_valid_uuid4(cid) and fpath:
            out.append(
                {
                    "node_id": node_id_str,
                    "file_path": str(fpath),
                    "cst_node_id": str(cid).strip(),
                }
            )
    for row in methods_res.get("data", []) or []:
        class_name = row.get("class_name") or row["class_name"]
        method_name = row.get("method_name") or row["method_name"]
        node_id_str = f"{class_name}.{method_name}"
        if node_id_str not in to_node_ids:
            continue
        cid = row.get("cst_node_id")
        fpath = row.get("file_path")
        if is_valid_uuid4(cid) and fpath:
            out.append(
                {
                    "node_id": node_id_str,
                    "file_path": str(fpath),
                    "cst_node_id": str(cid).strip(),
                }
            )
    return out
