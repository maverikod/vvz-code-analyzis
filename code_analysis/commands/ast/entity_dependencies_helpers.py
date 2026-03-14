"""
Helpers for entity dependencies/dependents: DB queries and entity resolution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import uuid
from typing import Any, Dict, List, Optional

CALLER_TYPES = ("class", "method", "function")
CALLEE_TYPES = ("class", "method", "function")


def is_valid_uuid4(value: Optional[str]) -> bool:
    """Return True if value is non-empty and valid UUID4 string."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    try:
        u = uuid.UUID(s, version=4)
        return str(u) == s
    except (ValueError, TypeError):
        return False


def row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert sqlite Row or dict to dict."""
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def path_by_file_ids(
    db: Any, file_ids: List[Optional[int]]
) -> Dict[Optional[int], str]:
    """Build mapping file_id -> path by querying files table."""
    ids = [fid for fid in file_ids if fid is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    result = db.execute(
        f"SELECT id, path FROM files WHERE id IN ({placeholders})",
        tuple(ids),
    )
    rows = result.get("data") or []
    path_by_id: Dict[Optional[int], str] = {}
    for r in rows:
        d = row_to_dict(r)
        path_by_id[d["id"]] = d.get("path", "")
    return path_by_id


def get_entity_dependencies_via_execute(
    db: Any, entity_type: str, entity_id: int
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
    result = db.execute(sql, (entity_id,))
    rows = result.get("data") or []
    if not rows:
        return []
    file_ids = list(
        {row_to_dict(r).get("file_id") for r in rows if row_to_dict(r).get("file_id")}
    )
    path_by_id = path_by_file_ids(db, file_ids)
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = row_to_dict(r)
        cst_node_id = d.get("cst_node_id")
        if not is_valid_uuid4(cst_node_id):
            continue
        if d.get("callee_class_id") is not None:
            callee_type, callee_id = "class", d["callee_class_id"]
        elif d.get("callee_method_id") is not None:
            callee_type, callee_id = "method", d["callee_method_id"]
        else:
            callee_type, callee_id = "function", d["callee_function_id"]
        file_id = d.get("file_id")
        out.append(
            {
                "callee_entity_type": callee_type,
                "callee_entity_id": callee_id,
                "ref_type": d.get("ref_type", ""),
                "file_path": path_by_id.get(file_id, ""),
                "line": d.get("line"),
                "cst_node_id": cst_node_id,
            }
        )
    return out


def resolve_entity_id_by_name(
    db: Any,
    project_id: str,
    entity_type: str,
    entity_name: str,
    target_class: Optional[str] = None,
) -> Optional[int]:
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
    db: Any, entity_type: str, entity_id: int
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
    result = db.execute(sql, (entity_id,))
    rows = result.get("data") or []
    if not rows:
        return []
    file_ids = list(
        {row_to_dict(r).get("file_id") for r in rows if row_to_dict(r).get("file_id")}
    )
    path_by_id = path_by_file_ids(db, file_ids)
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = row_to_dict(r)
        cst_node_id = d.get("cst_node_id")
        if not is_valid_uuid4(cst_node_id):
            continue
        if d.get("caller_class_id") is not None:
            caller_type, caller_id = "class", d["caller_class_id"]
        elif d.get("caller_method_id") is not None:
            caller_type, caller_id = "method", d["caller_method_id"]
        else:
            caller_type, caller_id = "function", d["caller_function_id"]
        file_id = d.get("file_id")
        out.append(
            {
                "caller_entity_type": caller_type,
                "caller_entity_id": caller_id,
                "ref_type": d.get("ref_type", ""),
                "file_path": path_by_id.get(file_id, ""),
                "line": d.get("line"),
                "cst_node_id": cst_node_id,
            }
        )
    return out
