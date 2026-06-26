"""
Resolver-based circular-import detection for project integrity.

Replaces the exact-dotted-path SQL matcher (``import_cycles_sql``), which could
not match bare/relative import module strings (e.g. ``from tree_builder_index
import X`` stored as ``module='tree_builder_index'``) against full path-derived
module keys, and so reported ZERO cycles where ``analyze_tree`` reported several
(TZ-CA-INDEX-INTEGRITY-001 C-3).

This uses the SAME ``ModulePathResolver`` + ``find_cycles`` as ``analyze_tree``
(both now in ``core.import_graph``), so the two detectors agree by construction.
Returns cycles as lists of ``file_id`` strings, matching the shape the issues
registry already consumes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from code_analysis.core.import_graph import ModulePathResolver, find_cycles
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE

DEFAULT_MAX_CHAIN_DEPTH = 10


def _rv(row: Any, key: str) -> Any:
    """Return rv."""
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _rel_of(
    path_abs: Optional[str], relative_path: Optional[str], root: Path
) -> Optional[str]:
    """Return rel of."""
    if relative_path:
        return str(relative_path).replace("\\", "/").lstrip("/")
    if path_abs:
        try:
            return str(Path(path_abs).resolve().relative_to(root)).replace("\\", "/")
        except (ValueError, OSError):
            return None
    return None


def fetch_import_cycles_resolver(
    database: Any,
    project_id: str,
    project_root: Path,
    *,
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
) -> List[List[str]]:
    """Detect circular imports project-wide via the shared resolver.

    ``max_depth`` is accepted for signature compatibility; SCC detection finds
    cycles of any length and does not need a hop bound.
    """
    file_res = database.execute(
        f"SELECT id, path, relative_path FROM files "
        f"WHERE project_id = ? AND {WHERE_FILES_ACTIVE}",
        (project_id,),
    )
    file_rows = (
        file_res.get("data", []) if isinstance(file_res, dict) else (file_res or [])
    )

    rel_by_id: dict[str, str] = {}
    id_by_rel: dict[str, str] = {}
    for row in file_rows:
        fid = str(_rv(row, "id"))
        rel = _rel_of(_rv(row, "path"), _rv(row, "relative_path"), project_root)
        if not rel:
            continue
        rel_by_id[fid] = rel
        id_by_rel[rel] = fid

    resolver = ModulePathResolver(rel_by_id.values())

    imp_res = database.execute(
        """
        SELECT i.file_id, i.module, i.name, i.import_type
        FROM imports i
        JOIN files f ON f.id = i.file_id
        WHERE f.project_id = ?
        """,
        (project_id,),
    )
    imp_rows = imp_res.get("data", []) if isinstance(imp_res, dict) else (imp_res or [])

    adjacency: dict[str, set[str]] = {fid: set() for fid in rel_by_id}
    for row in imp_rows:
        src_id = str(_rv(row, "file_id"))
        src_rel = rel_by_id.get(src_id)
        if not src_rel:
            continue
        resolved = resolver.resolve(
            module=_rv(row, "module"),
            name=_rv(row, "name"),
            import_type=_rv(row, "import_type"),
            importer_rel=src_rel,
        )
        if resolved.kind == "project" and resolved.rel_path:
            tgt_id = id_by_rel.get(resolved.rel_path)
            if tgt_id and tgt_id != src_id:
                adjacency[src_id].add(tgt_id)

    return find_cycles(adjacency)
