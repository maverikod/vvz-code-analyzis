"""
Helpers for entity dependencies/dependents: DB queries and entity resolution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from typing import Any, Dict, List, Optional

from ...core.file_identity import PathLike, relative_path_for_indexed_row
from ...core.uuid_validation import is_valid_uuid4

CALLER_TYPES = ("class", "method", "function")
CALLEE_TYPES = ("class", "method", "function")


def _bind_entity_id_for_cross_ref(entity_id: Any) -> Any:
    """Bind value for UUID/text id columns (PostgreSQL); SQLite tolerates str for int PKs."""
    if entity_id is None:
        return None
    if isinstance(entity_id, uuid.UUID):
        return str(entity_id)
    if isinstance(entity_id, str):
        return entity_id
    return str(entity_id)


def row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert sqlite Row or dict to dict."""
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def path_by_file_ids(
    db: Any, file_ids: List[Any], project_root: Optional[PathLike] = None
) -> Dict[Any, str]:
    """Build mapping file_id -> project-relative POSIX path by querying files table."""
    ids = [fid for fid in file_ids if fid is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    result = db.execute(
        f"SELECT id, path, relative_path FROM files WHERE id IN ({placeholders})",
        tuple(ids),
    )
    rows = result.get("data") or []
    path_by_id: Dict[Any, str] = {}
    for r in rows:
        d = row_to_dict(r)
        path_by_id[d["id"]] = relative_path_for_indexed_row(d, project_root)
    return path_by_id


def get_entity_dependencies_via_execute(
    db: Any,
    entity_type: str,
    entity_id: Any,
    project_root: Optional[PathLike] = None,
) -> List[Dict[str, Any]]:
    """Get dependencies by querying entity_cross_ref (caller -> callee)."""
    if entity_type == "class":
        col = "e.caller_class_id"
    elif entity_type == "method":
        col = "e.caller_method_id"
    elif entity_type == "function":
        col = "e.caller_function_id"
    else:
        return []
    sql = f"""
        SELECT e.callee_class_id, e.callee_method_id, e.callee_function_id,
               e.ref_type, e.file_id, e.line,
               COALESCE(c.cst_node_id, m.cst_node_id, fn.cst_node_id) AS cst_node_id
        FROM entity_cross_ref e
        LEFT JOIN classes c ON e.callee_class_id = c.id
        LEFT JOIN methods m ON e.callee_method_id = m.id
        LEFT JOIN functions fn ON e.callee_function_id = fn.id
        WHERE {col} = ?
    """
    bind_id = _bind_entity_id_for_cross_ref(entity_id)
    result = db.execute(sql, (bind_id,))
    rows = result.get("data") or []
    if not rows:
        return []
    file_ids = list(
        {row_to_dict(r).get("file_id") for r in rows if row_to_dict(r).get("file_id")}
    )
    path_by_id = path_by_file_ids(db, file_ids, project_root)
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = row_to_dict(r)
        cst_node_id = d.get("cst_node_id")
        if d.get("callee_class_id") is not None:
            callee_type, callee_id = "class", d["callee_class_id"]
        elif d.get("callee_method_id") is not None:
            callee_type, callee_id = "method", d["callee_method_id"]
        else:
            callee_type, callee_id = "function", d["callee_function_id"]
        file_id = d.get("file_id")
        entry: Dict[str, Any] = {
            "callee_entity_type": callee_type,
            "callee_entity_id": callee_id,
            "ref_type": d.get("ref_type", ""),
            "file_path": path_by_id.get(file_id, ""),
            "line": d.get("line"),
        }
        if is_valid_uuid4(cst_node_id):
            entry["cst_node_id"] = cst_node_id
        out.append(entry)
    return out


def resolve_entity_id_by_name(
    db: Any,
    project_id: str,
    entity_type: str,
    entity_name: str,
    target_class: Optional[str] = None,
) -> Optional[Any]:
    """Resolve entity name to database id within the project."""
    if entity_type == "class":
        r = db.execute(
            """
            SELECT c.id FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ? AND c.name = ?
            ORDER BY f.path LIMIT 1
            """,
            (project_id, entity_name),
        )
    elif entity_type == "function":
        r = db.execute(
            """
            SELECT fn.id FROM functions fn
            JOIN files f ON fn.file_id = f.id
            WHERE f.project_id = ? AND fn.name = ?
            ORDER BY f.path LIMIT 1
            """,
            (project_id, entity_name),
        )
    elif entity_type == "method":
        if target_class:
            r = db.execute(
                """
                SELECT m.id FROM methods m
                JOIN classes c ON m.class_id = c.id
                JOIN files f ON c.file_id = f.id
                WHERE f.project_id = ? AND c.name = ? AND m.name = ?
                ORDER BY f.path LIMIT 1
                """,
                (project_id, target_class, entity_name),
            )
        else:
            r = db.execute(
                """
                SELECT m.id FROM methods m
                JOIN classes c ON m.class_id = c.id
                JOIN files f ON c.file_id = f.id
                WHERE f.project_id = ? AND m.name = ?
                ORDER BY f.path LIMIT 1
                """,
                (project_id, entity_name),
            )
    else:
        return None
    rows = r.get("data") or []
    if not rows:
        return None
    return row_to_dict(rows[0]).get("id")


def get_entity_dependents_via_execute(
    db: Any,
    entity_type: str,
    entity_id: Any,
    project_root: Optional[PathLike] = None,
) -> List[Dict[str, Any]]:
    """Get dependents by querying entity_cross_ref (callee -> caller)."""
    if entity_type == "class":
        col = "e.callee_class_id"
    elif entity_type == "method":
        col = "e.callee_method_id"
    elif entity_type == "function":
        col = "e.callee_function_id"
    else:
        return []
    sql = f"""
        SELECT e.caller_class_id, e.caller_method_id, e.caller_function_id,
               e.ref_type, e.file_id, e.line,
               COALESCE(c.cst_node_id, m.cst_node_id, fn.cst_node_id) AS cst_node_id
        FROM entity_cross_ref e
        LEFT JOIN classes c ON e.caller_class_id = c.id
        LEFT JOIN methods m ON e.caller_method_id = m.id
        LEFT JOIN functions fn ON e.caller_function_id = fn.id
        WHERE {col} = ?
    """
    bind_id = _bind_entity_id_for_cross_ref(entity_id)
    result = db.execute(sql, (bind_id,))
    rows = result.get("data") or []
    if not rows:
        return []
    file_ids = list(
        {row_to_dict(r).get("file_id") for r in rows if row_to_dict(r).get("file_id")}
    )
    path_by_id = path_by_file_ids(db, file_ids, project_root)
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = row_to_dict(r)
        cst_node_id = d.get("cst_node_id")
        if d.get("caller_class_id") is not None:
            caller_type, caller_id = "class", d["caller_class_id"]
        elif d.get("caller_method_id") is not None:
            caller_type, caller_id = "method", d["caller_method_id"]
        else:
            caller_type, caller_id = "function", d["caller_function_id"]
        file_id = d.get("file_id")
        entry: Dict[str, Any] = {
            "caller_entity_type": caller_type,
            "caller_entity_id": caller_id,
            "ref_type": d.get("ref_type", ""),
            "file_path": path_by_id.get(file_id, ""),
            "line": d.get("line"),
        }
        if is_valid_uuid4(cst_node_id):
            entry["cst_node_id"] = cst_node_id
        out.append(entry)
    return out
