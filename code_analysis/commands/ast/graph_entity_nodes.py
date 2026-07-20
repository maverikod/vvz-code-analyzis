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

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ...core.file_identity import PathLike, relative_path_for_indexed_row


def resolve_usage_target_cst_node_id(
    db: Any,
    project_id: str,
    file_id: int,
    entity_type: str,
    name: str,
    class_name: Optional[str],
    is_valid_uuid4: Callable[[Any], bool],
) -> Optional[Tuple[str, str]]:
    """
    Resolve (cst_node_id, file_path) for a usage target scoped to one file row.

    Used by call_graph export to disambiguate same-named symbols in different files.
    """
    row: Any = None
    et = (entity_type or "").strip().lower()
    if et == "class":
        row = db._fetchone(
            "SELECT c.cst_node_id AS cst_node_id, f.path AS path FROM classes c "
            "JOIN files f ON f.id = c.file_id "
            "WHERE f.project_id = ? AND c.file_id = ? AND c.name = ?",
            (project_id, file_id, name),
        )
    elif et == "function":
        row = db._fetchone(
            "SELECT fn.cst_node_id AS cst_node_id, f.path AS path FROM functions fn "
            "JOIN files f ON f.id = fn.file_id "
            "WHERE f.project_id = ? AND fn.file_id = ? AND fn.name = ?",
            (project_id, file_id, name),
        )
    elif et == "method" and class_name:
        row = db._fetchone(
            "SELECT m.cst_node_id AS cst_node_id, f.path AS path FROM methods m "
            "JOIN classes c ON c.id = m.class_id "
            "JOIN files f ON f.id = c.file_id "
            "WHERE f.project_id = ? AND c.file_id = ? AND c.name = ? AND m.name = ?",
            (project_id, file_id, class_name, name),
        )
    else:
        return None
    if not row:
        return None
    cid = (
        row["cst_node_id"]
        if isinstance(row, dict)
        else getattr(row, "cst_node_id", None)
    )
    path = row["path"] if isinstance(row, dict) else getattr(row, "path", None)
    if cid is None or path is None:
        return None
    if not is_valid_uuid4(cid):
        return None
    return (str(cid).strip(), str(path))


def build_entity_nodes_hierarchy(
    rows: List[Any],
    is_valid_uuid4: Callable[[Any], bool],
    project_root: Optional[PathLike] = None,
) -> List[Dict[str, str]]:
    """Build entity_nodes from hierarchy query rows (classes with file_path, cst_node_id).

    Only includes entries with valid UUID4 cst_node_id and non-empty file_path.
    Aligns with snapshot node identity: cst_node_id equals file_tree_snapshot_nodes.node_id.
    ``file_path`` in the output is project-relative POSIX.

    Args:
        rows: Rows from SELECT c.name, c.bases, f.path, f.relative_path, c.cst_node_id ...
        is_valid_uuid4: Predicate for valid UUID4 string.
        project_root: Project root, used for the legacy-row relative-path fallback.

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
        relative_path_val = r.get("relative_path") if hasattr(r, "get") else None
        out.append(
            {
                "node_id": node_id_str,
                "file_path": relative_path_for_indexed_row(
                    {"path": file_path_val, "relative_path": relative_path_val},
                    project_root,
                ),
                "cst_node_id": str(cid).strip(),
            }
        )
    return out


def build_entity_nodes_call_graph(
    db: Any,
    project_id: str,
    to_node_ids: Set[str],
    is_valid_uuid4: Callable[[Any], bool],
    project_root: Optional[PathLike] = None,
) -> List[Dict[str, str]]:
    """Resolve call_graph 'to' node ids to entities with file_path and cst_node_id.

    Queries classes, functions, methods with valid cst_node_id and appends
    matching entity payloads. Only includes entries with valid UUID4.
    cst_node_id aligns with file_tree_snapshot_nodes.node_id for tree correlation.
    ``file_path`` in the output is project-relative POSIX.

    Args:
        db: Database driver with execute() returning {"data": list of rows}.
        project_id: Project UUID.
        to_node_ids: Set of destination node id strings (e.g. "Class.method" or "func").
        is_valid_uuid4: Predicate for valid UUID4 string.
        project_root: Project root, used for the legacy-row relative-path fallback.

    Returns:
        List of {"node_id", "file_path", "cst_node_id"} dicts; all have valid UUID4.
    """
    out: List[Dict[str, str]] = []
    classes_res = db.execute(
        """
        SELECT c.name, f.path AS file_path, f.relative_path, c.cst_node_id
        FROM classes c
        JOIN files f ON f.id = c.file_id
        WHERE f.project_id = ? AND c.cst_node_id IS NOT NULL
        AND c.cst_node_id != ''
        """,
        (project_id,),
    )
    funcs_res = db.execute(
        """
        SELECT func.name, f.path AS file_path, f.relative_path, func.cst_node_id
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
               f.path AS file_path, f.relative_path, m.cst_node_id
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
                    "file_path": relative_path_for_indexed_row(
                        {"path": fpath, "relative_path": row.get("relative_path")},
                        project_root,
                    ),
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
                    "file_path": relative_path_for_indexed_row(
                        {"path": fpath, "relative_path": row.get("relative_path")},
                        project_root,
                    ),
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
                    "file_path": relative_path_for_indexed_row(
                        {"path": fpath, "relative_path": row.get("relative_path")},
                        project_root,
                    ),
                    "cst_node_id": str(cid).strip(),
                }
            )
    return out
