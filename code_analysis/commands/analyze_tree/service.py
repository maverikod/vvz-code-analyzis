"""
analyze_tree shared core (atom A-CORE).

Enumerates the real files under ``roots`` (disk = existence truth), runs the
per-file checksum staleness gate, builds the module-resolved relation graph once,
then hands a ``CoreData`` to the selected mode. Read-only: no project source,
sidecar, or DB writes.

Layering: the command stays thin and delegates here; this module owns DB access
via the shared ``DatabaseClient`` (the same universal entrypoint other read-only
commands use — see export_graph).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum

from . import staleness as st
from .core_types import CoreData, Edge
from .modes import run_mode
from .resolver import ModulePathResolver

logger = logging.getLogger(__name__)

# Directories never worth walking for a sub-tree analysis.
_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".idea",
        ".vscode",
        ".tox",
    }
)


def _rv(row: Any, key: str) -> Any:
    """Read a column from a dict-like or sequence-mapping DB row."""
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _norm_root(root: str) -> str:
    """Normalize a project-relative root prefix (forward slashes, no trailing /)."""
    r = str(root).replace("\\", "/").strip()
    while r.startswith("./"):
        r = r[2:]
    return r.strip("/")


def _under_roots(rel: str, roots: list[str]) -> bool:
    """True when ``rel`` is at or under any normalized root prefix."""
    for r in roots:
        if r == "" or rel == r or rel.startswith(r + "/"):
            return True
    return False


def _rel_of(path_abs: Optional[str], relative_path: Optional[str], root: Path) -> Optional[str]:
    """Project-relative path for a file row, preferring an explicit relative_path."""
    if relative_path:
        return str(relative_path).replace("\\", "/").lstrip("/")
    if path_abs:
        try:
            return str(Path(path_abs).resolve().relative_to(root)).replace("\\", "/")
        except (ValueError, OSError):
            return None
    return None


def _enumerate_disk_py_files(root: Path, roots: list[str]) -> list[str]:
    """Read-only walk: project-relative ``.py`` paths under the given roots."""
    found: list[str] = []
    seen: set[str] = set()
    for r in roots:
        start = (root / r).resolve() if r else root
        if not start.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                abs_p = Path(dirpath) / fn
                try:
                    rel = str(abs_p.resolve().relative_to(root)).replace("\\", "/")
                except (ValueError, OSError):
                    continue
                if rel not in seen:
                    seen.add(rel)
                    found.append(rel)
    return sorted(found)


def _content_checksum(root: Path, rel: str) -> Optional[str]:
    """SHA-256 of the on-disk content, or None when unreadable as UTF-8 text."""
    try:
        text = (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return compute_content_checksum(text)


def build_core(
    *,
    db: Any,
    project_id: str,
    project_root: Path,
    roots: list[str],
    mode: str,
    limit: int,
) -> CoreData:
    """Compute the shared core for the sub-tree (A-CORE)."""
    norm_roots = [_norm_root(r) for r in roots]

    # --- project file index (all files, for resolution + inbound) ---
    res = db.execute(
        """
        SELECT id, path, relative_path, tree_checksum
        FROM files
        WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)
        """,
        (project_id,),
    )
    file_rows = res.get("data", []) if isinstance(res, dict) else (res or [])

    rel_by_file_id: dict[str, str] = {}
    checksum_by_rel: dict[str, Optional[str]] = {}
    project_files: set[str] = set()
    for row in file_rows:
        fid = _rv(row, "id")
        rel = _rel_of(_rv(row, "path"), _rv(row, "relative_path"), project_root)
        if not rel:
            continue
        rel_by_file_id[str(fid)] = rel
        checksum_by_rel[rel] = _rv(row, "tree_checksum")
        project_files.add(rel)

    resolver = ModulePathResolver(project_files)

    # --- internal files: disk existence truth, union with indexed files ---
    disk_files = _enumerate_disk_py_files(project_root, norm_roots)
    internal_set: set[str] = set(disk_files)
    for rel in project_files:
        if _under_roots(rel, norm_roots):
            internal_set.add(rel)
    internal_files = sorted(internal_set)

    # --- active edit sessions (DB-backed, cross-process truth) ---
    held: set[str] = set()
    try:
        lease_res = db.execute(
            "SELECT file_path FROM file_advisory_lock_leases WHERE project_id = ?",
            (project_id,),
        )
        lease_rows = (
            lease_res.get("data", []) if isinstance(lease_res, dict) else (lease_res or [])
        )
        for row in lease_rows:
            fp = _rv(row, "file_path")
            if fp:
                held.add(str(fp).replace("\\", "/").lstrip("/"))
    except Exception as exc:  # advisory-lease table is optional/best-effort
        logger.debug("analyze_tree: advisory lease query failed: %s", exc)

    # --- staleness gate per internal file ---
    counts = st.empty_counts()
    rebuilt_sample: list[str] = []
    skipped_sample: list[str] = []
    for rel in internal_files:
        in_db = rel in project_files
        active = rel in held
        current = _content_checksum(project_root, rel) if in_db else None
        bucket = st.classify_file(
            in_db=in_db,
            stored_checksum=checksum_by_rel.get(rel),
            current_checksum=current,
            active_session=active,
        )
        counts[bucket] += 1
        if bucket == st.REBUILT and len(rebuilt_sample) < 50:
            rebuilt_sample.append(rel)
        elif bucket == st.SKIPPED_ACTIVE_SESSION and len(skipped_sample) < 50:
            skipped_sample.append(rel)

    staleness = {
        "counts": counts,
        "rebuilt": rebuilt_sample,
        "skipped_active_session": skipped_sample,
    }

    # --- relation graph (whole project, so inbound from outside is visible) ---
    imp_res = db.execute(
        """
        SELECT i.file_id, i.module, i.name, i.import_type
        FROM imports i
        JOIN files f ON f.id = i.file_id
        WHERE f.project_id = ?
        """,
        (project_id,),
    )
    imp_rows = imp_res.get("data", []) if isinstance(imp_res, dict) else (imp_res or [])
    edges: list[Edge] = []
    truncated = False
    for row in imp_rows:
        if len(edges) >= limit:
            truncated = True
            break
        src = rel_by_file_id.get(str(_rv(row, "file_id")))
        if not src:
            continue
        resolved = resolver.resolve(
            module=_rv(row, "module"),
            name=_rv(row, "name"),
            import_type=_rv(row, "import_type"),
            importer_rel=src,
        )
        edges.append(
            Edge(
                src=src,
                kind=resolved.kind,
                module=resolved.module,
                target_rel=resolved.rel_path,
            )
        )

    core = CoreData(
        roots=norm_roots,
        internal_files=internal_files,
        internal_set=internal_set,
        project_files=project_files,
        edges=edges,
        staleness=staleness,
        truncated=truncated,
    )

    if mode == "structure":
        core.structure_by_file = _load_structure(
            db, project_id, internal_set, rel_by_file_id
        )
    return core


def _load_structure(
    db: Any,
    project_id: str,
    internal_set: set[str],
    rel_by_file_id: dict[str, str],
) -> dict[str, dict]:
    """Per-file composition (classes+methods, functions) for the sub-tree files."""
    out: dict[str, dict] = {rel: {"classes": [], "functions": []} for rel in internal_set}

    cls_res = db.execute(
        """
        SELECT c.id, c.file_id, c.name, c.line, c.end_line
        FROM classes c
        JOIN files f ON f.id = c.file_id
        WHERE f.project_id = ?
        """,
        (project_id,),
    )
    cls_rows = cls_res.get("data", []) if isinstance(cls_res, dict) else (cls_res or [])
    class_by_id: dict[str, dict] = {}
    for row in cls_rows:
        rel = rel_by_file_id.get(str(_rv(row, "file_id")))
        if rel not in internal_set:
            continue
        entry = {
            "name": _rv(row, "name"),
            "line": _rv(row, "line"),
            "end_line": _rv(row, "end_line"),
            "methods": [],
        }
        class_by_id[str(_rv(row, "id"))] = entry
        out[rel]["classes"].append(entry)

    if class_by_id:
        m_res = db.execute(
            """
            SELECT m.class_id, m.name, m.line
            FROM methods m
            JOIN classes c ON c.id = m.class_id
            JOIN files f ON f.id = c.file_id
            WHERE f.project_id = ?
            """,
            (project_id,),
        )
        m_rows = m_res.get("data", []) if isinstance(m_res, dict) else (m_res or [])
        for row in m_rows:
            cls = class_by_id.get(str(_rv(row, "class_id")))
            if cls is not None:
                cls["methods"].append(
                    {"name": _rv(row, "name"), "line": _rv(row, "line")}
                )

    fn_res = db.execute(
        """
        SELECT fn.file_id, fn.name, fn.line, fn.end_line
        FROM functions fn
        JOIN files f ON f.id = fn.file_id
        WHERE f.project_id = ?
        """,
        (project_id,),
    )
    fn_rows = fn_res.get("data", []) if isinstance(fn_res, dict) else (fn_res or [])
    for row in fn_rows:
        rel = rel_by_file_id.get(str(_rv(row, "file_id")))
        if rel not in internal_set:
            continue
        out[rel]["functions"].append(
            {"name": _rv(row, "name"), "line": _rv(row, "line"), "end_line": _rv(row, "end_line")}
        )
    return out


def analyze_tree_json(
    *,
    db: Any,
    project_id: str,
    project_root: Path,
    roots: list[str],
    mode: str,
    include_stdlib: bool,
    with_verdict: bool,
    limit: int,
    keep_seeds: Optional[tuple[str, ...]] = None,
    parameterize_seeds: Optional[tuple[str, ...]] = None,
) -> dict:
    """Run the shared core + selected mode, returning the JSON ``data`` block."""
    core = build_core(
        db=db,
        project_id=project_id,
        project_root=project_root,
        roots=roots,
        mode=mode,
        limit=limit,
    )
    mode_blocks = run_mode(
        mode,
        core,
        include_stdlib=include_stdlib,
        with_verdict=with_verdict,
        keep_seeds=keep_seeds,
        parameterize_seeds=parameterize_seeds,
    )
    data: dict = {
        "mode": mode,
        "roots": core.roots,
        "staleness": core.staleness,
        "truncated": core.truncated,
    }
    data.update(mode_blocks)
    return data
