"""
Shared file-path resolution helpers for AST MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.path_normalization import file_lookup_paths_for_project


def _candidate_fs_path(file_path: str, project_root: Path) -> Path:
    """Return candidate fs path."""
    p = Path(file_path)
    if p.is_absolute():
        return p.resolve()
    return (project_root / p).resolve()


def resolve_project_file_record(
    db: Any,
    project_id: str,
    project_root: Path,
    file_path: str,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    """
    Resolve file row by project-relative or absolute path.

    Returns:
        {
            "file_record": Optional[dict],
            "normalized_file_path": str,
            "exists_on_disk": bool,
        }
    """
    normalized_input = str(Path(file_path)).replace("\\", "/")
    fs_candidate = _candidate_fs_path(file_path, project_root)
    exists_on_disk = fs_candidate.exists() and fs_candidate.is_file()

    abs_keys, rel_keys = file_lookup_paths_for_project(file_path, project_root)
    rel_keys = [k.replace("\\", "/") for k in rel_keys if isinstance(k, str)]

    # Keep rows where deleted is NULL/false and exclude only explicit true.
    # This is backend-safe for PostgreSQL boolean columns.
    where_deleted = "" if include_deleted else " AND f.deleted IS NOT TRUE"
    file_record: Optional[Dict[str, Any]] = None

    # 1) Exact matching against both absolute and project-relative columns.
    exact_parts: List[str] = []
    exact_params: List[Any] = [project_id]
    if abs_keys:
        placeholders = ",".join("?" for _ in abs_keys)
        exact_parts.append(f"f.path IN ({placeholders})")
        exact_params.extend(abs_keys)
    if rel_keys:
        placeholders = ",".join("?" for _ in rel_keys)
        exact_parts.append(f"f.relative_path IN ({placeholders})")
        exact_params.extend(rel_keys)
    if exact_parts:
        exact_sql = (
            "SELECT f.* FROM files f WHERE f.project_id = ?"
            + where_deleted
            + " AND ("
            + " OR ".join(exact_parts)
            + ") ORDER BY f.id LIMIT 1"
        )
        exact_rows = db.execute(exact_sql, tuple(exact_params)).get("data", [])
        if exact_rows:
            file_record = exact_rows[0]

    # 2) Fallback suffix matching for legacy rows (versioned or stale paths).
    if not file_record and rel_keys:
        like_parts: List[str] = []
        like_params: List[Any] = [project_id]
        for rel in rel_keys:
            like_parts.append("f.path LIKE ?")
            like_params.append(f"%{rel}")
            like_parts.append("f.relative_path LIKE ?")
            like_params.append(f"%{rel}")
        like_sql = (
            "SELECT f.* FROM files f WHERE f.project_id = ?"
            + where_deleted
            + " AND ("
            + " OR ".join(like_parts)
            + ") ORDER BY LENGTH(f.path) ASC, f.id ASC LIMIT 1"
        )
        like_rows = db.execute(like_sql, tuple(like_params)).get("data", [])
        if like_rows:
            file_record = like_rows[0]

    normalized_file_path = rel_keys[0] if rel_keys else normalized_input
    return {
        "file_record": file_record,
        "normalized_file_path": normalized_file_path,
        "exists_on_disk": exists_on_disk,
    }
