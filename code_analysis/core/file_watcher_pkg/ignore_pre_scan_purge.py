"""
Pre-scan ignore purge: remove DB rows for paths excluded by watcher ignore rules.

DB-only (no disk deletes). Uses the same traversal pruning (``should_skip_dir``)
and ``should_ignore_path`` rules as ``scan_directory``, then one logical write
with FK-safe DELETE order aligned to
``build_delete_project_full_clear_batch`` (scoped to a temp table of file ids).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Sequence, Set, Tuple

from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    database_has_sqlite_code_content_fts,
)

from .scanner import is_traversable_venv_root, should_ignore_path, should_skip_dir

logger = logging.getLogger(__name__)

TEMP_PURGE_TABLE = "watcher_ignore_purge_ids"
_PURGE = f"SELECT id FROM {TEMP_PURGE_TABLE}"

_INSERT_CHUNK = 400


def _query_file_rows(database: Any, sql: str, params: tuple[Any, ...]) -> List[dict[str, Any]]:
    if hasattr(database, "_fetchall"):
        rows = database._fetchall(sql, params)
        return list(rows) if isinstance(rows, list) else []
    out = database.execute(sql, params)
    if not isinstance(out, dict):
        return []
    data = out.get("data")
    return list(data) if isinstance(data, list) else []


def collect_file_ids_to_purge_for_ignore_policy(
    database: Any,
    project_id: str,
    ignore_patterns: Sequence[str],
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
) -> List[int]:
    """
    Return ``files.id`` for active rows whose path should be ignored by scanner rules.

    Matches ``scan_directory`` / ``should_ignore_path`` semantics (including
    ``ignore_exception_files`` and venv allowlist).
    """
    from code_analysis.core.file_watcher_pkg.scanner import should_ignore_path

    rows = _query_file_rows(
        database,
        f"SELECT id, path FROM files WHERE project_id = ? AND {WHERE_FILES_ACTIVE}",
        (project_id,),
    )
    patterns = list(ignore_patterns)
    out: List[int] = []
    for row in rows:
        fid = row.get("id")
        pstr = row.get("path")
        if fid is None or not pstr:
            continue
        path = Path(str(pstr))
        if should_ignore_path(
            path,
            patterns,
            allowed_venv_py_files=allowed_venv_py_files,
            ignore_exception_files=ignore_exception_files,
        ):
            out.append(int(fid))
    return out


def list_non_ignored_code_files_under_root(
    project_root: Path,
    ignore_patterns: Sequence[str],
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
) -> Tuple[Path, ...]:
    """
    Walk ``project_root`` with directory pruning (``should_skip_dir`` + ``should_ignore_path``).

    Returns file paths that are **not** ignored (pruned tree, same rules as
    ``scan_directory``). Used for tests and diagnostics; purge selection uses
    ``collect_file_ids_to_purge_for_ignore_policy`` on DB rows.
    """
    patterns = list(ignore_patterns)
    root = project_root.resolve()
    yielded: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dir_path = Path(dirpath)
        if should_ignore_path(
            dir_path,
            patterns,
            allowed_venv_py_files=allowed_venv_py_files,
            ignore_exception_files=ignore_exception_files,
        ):
            dirnames[:] = []
            continue
        pruned_dirs: List[str] = []
        for name in sorted(dirnames):
            child = dir_path / name
            if should_skip_dir(child, walk_root=root):
                continue
            if should_ignore_path(
                child,
                patterns,
                allowed_venv_py_files=allowed_venv_py_files,
                ignore_exception_files=ignore_exception_files,
            ) and not is_traversable_venv_root(child):
                continue
            pruned_dirs.append(name)
        dirnames[:] = pruned_dirs
        for name in filenames:
            fp = dir_path / name
            if should_ignore_path(
                fp,
                patterns,
                allowed_venv_py_files=allowed_venv_py_files,
                ignore_exception_files=ignore_exception_files,
            ):
                continue
            if fp.is_file():
                yielded.append(fp)
    return tuple(yielded)


def _pair_issues_delete_for_purge_temp() -> Tuple[str, tuple[Any, ...]]:
    sql = f"""
DELETE FROM issues WHERE
  file_id IN ({_PURGE})
  OR class_id IN (SELECT id FROM classes WHERE file_id IN ({_PURGE}))
  OR method_id IN (
    SELECT id FROM methods WHERE class_id IN (
      SELECT id FROM classes WHERE file_id IN ({_PURGE})
    )
  )
  OR function_id IN (SELECT id FROM functions WHERE file_id IN ({_PURGE}))
""".strip()
    return sql, ()


def _pair_entity_cross_ref_delete_for_purge_temp() -> Tuple[str, tuple[Any, ...]]:
    sql = f"""
DELETE FROM entity_cross_ref WHERE
  file_id IN ({_PURGE})
  OR caller_class_id IN (SELECT id FROM classes WHERE file_id IN ({_PURGE}))
  OR callee_class_id IN (SELECT id FROM classes WHERE file_id IN ({_PURGE}))
  OR caller_method_id IN (SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN ({_PURGE})))
  OR callee_method_id IN (SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN ({_PURGE})))
  OR caller_function_id IN (SELECT id FROM functions WHERE file_id IN ({_PURGE}))
  OR callee_function_id IN (SELECT id FROM functions WHERE file_id IN ({_PURGE}))
""".strip()
    return sql, ()


def build_ignore_purge_sql_batch(
    project_id: str,
    file_ids: Sequence[int],
    *,
    include_code_content_fts: bool = True,
) -> List[Tuple[str, tuple[Any, ...]]]:
    """
    Build (sql, params) ops: CREATE TEMP, INSERT ids, then FK-safe DELETEs.

    Caller must run inside ``execute_logical_write_operation`` on a single DB connection.
    """
    if not file_ids:
        return []
    pid = project_id
    ops: List[Tuple[str, tuple[Any, ...]]] = []

    ops.append((f"DROP TABLE IF EXISTS {TEMP_PURGE_TABLE}", ()))
    ops.append(
        (
            f"CREATE TEMP TABLE {TEMP_PURGE_TABLE} (id INTEGER NOT NULL PRIMARY KEY)",
            (),
        )
    )

    ids_list = [int(x) for x in file_ids]
    for i in range(0, len(ids_list), _INSERT_CHUNK):
        chunk = ids_list[i : i + _INSERT_CHUNK]
        placeholders = ",".join(["(?)"] * len(chunk))
        ops.append(
            (
                f"INSERT INTO {TEMP_PURGE_TABLE} (id) VALUES {placeholders}",
                tuple(chunk),
            )
        )

    # duplicate_occurrences: remove whole duplicate groups touching purged files
    ops.append(
        (
            f"DELETE FROM duplicate_occurrences WHERE duplicate_id IN ("
            f"SELECT DISTINCT duplicate_id FROM duplicate_occurrences "
            f"WHERE file_id IN ({_PURGE}))",
            (),
        )
    )
    ops.append(
        (
            "DELETE FROM code_duplicates WHERE project_id = ? AND NOT EXISTS ("
            "SELECT 1 FROM duplicate_occurrences o WHERE o.duplicate_id = code_duplicates.id)",
            (pid,),
        )
    )

    if include_code_content_fts:
        ops.append(
            (
                "DELETE FROM code_content_fts WHERE rowid IN ("
                f"SELECT id FROM code_content WHERE file_id IN ({_PURGE}))",
                (),
            )
        )

    ops.append(
        (f"DELETE FROM code_chunks WHERE file_id IN ({_PURGE})", ()),
    )

    ops.append(_pair_issues_delete_for_purge_temp())
    ops.append(_pair_entity_cross_ref_delete_for_purge_temp())

    ops.append(
        (
            f"DELETE FROM methods WHERE class_id IN ("
            f"SELECT id FROM classes WHERE file_id IN ({_PURGE}))",
            (),
        )
    )
    ops.append((f"DELETE FROM classes WHERE file_id IN ({_PURGE})", ()))
    ops.append((f"DELETE FROM functions WHERE file_id IN ({_PURGE})", ()))
    ops.append((f"DELETE FROM imports WHERE file_id IN ({_PURGE})", ()))
    ops.append((f"DELETE FROM code_content WHERE file_id IN ({_PURGE})", ()))
    ops.append((f"DELETE FROM ast_trees WHERE file_id IN ({_PURGE})", ()))
    ops.append((f"DELETE FROM cst_trees WHERE file_id IN ({_PURGE})", ()))
    ops.append((f"DELETE FROM usages WHERE file_id IN ({_PURGE})", ()))
    ops.append(
        (f"DELETE FROM comprehensive_analysis_results WHERE file_id IN ({_PURGE})", ())
    )

    ops.append(
        (
            "DELETE FROM file_tree_snapshot_nodes WHERE snapshot_id IN ("
            f"SELECT id FROM file_tree_snapshots WHERE file_id IN ({_PURGE}))",
            (),
        )
    )
    ops.append(
        (
            "DELETE FROM file_tree_snapshot_roots WHERE snapshot_id IN ("
            f"SELECT id FROM file_tree_snapshots WHERE file_id IN ({_PURGE}))",
            (),
        )
    )
    ops.append(
        (f"DELETE FROM file_tree_snapshots WHERE file_id IN ({_PURGE})", ()),
    )

    ops.append(
        (
            f"DELETE FROM indexing_errors WHERE project_id = ? AND file_path IN ("
            f"SELECT path FROM files WHERE id IN ({_PURGE}))",
            (pid,),
        )
    )

    ops.append(
        (
            f"DELETE FROM vector_index WHERE project_id = ? AND ("
            f"(entity_type = 'file' AND entity_id IN ({_PURGE})) OR "
            f"(entity_type = 'class' AND entity_id IN ("
            f"SELECT id FROM classes WHERE file_id IN ({_PURGE}))) OR "
            f"(entity_type = 'function' AND entity_id IN ("
            f"SELECT id FROM functions WHERE file_id IN ({_PURGE}))) OR "
            f"(entity_type = 'method' AND entity_id IN ("
            f"SELECT m.id FROM methods m JOIN classes c ON m.class_id = c.id "
            f"WHERE c.file_id IN ({_PURGE}))))",
            (pid,),
        )
    )

    ops.append((f"DELETE FROM files WHERE id IN ({_PURGE})", ()))

    return ops


def build_ignore_purge_logical_write_program(
    project_id: str,
    file_ids: Sequence[int],
    *,
    include_code_content_fts: bool = True,
) -> LogicalWriteProgramV1:
    """Single-batch logical write program for ignore purge."""
    batch = build_ignore_purge_sql_batch(
        project_id, file_ids, include_code_content_fts=include_code_content_fts
    )
    return {"batches": [batch]}


def try_unlink_faiss_index_for_project(
    project_id: str, config_path: Optional[Path]
) -> bool:
    """
    Best-effort remove project FAISS file so vector worker rebuilds from DB.

    Does not rebuild synchronously (avoids racing the vectorization process).
    Returns True if an index file was removed.
    """
    if config_path is None or not config_path.is_file():
        return False
    try:
        from code_analysis.core.storage_paths import (
            get_faiss_index_path,
            load_raw_config,
            resolve_storage_paths,
        )

        config_data = load_raw_config(config_path)
        storage = resolve_storage_paths(
            config_data=config_data, config_path=config_path
        )
        index_path = get_faiss_index_path(storage.faiss_dir, project_id)
        if index_path.is_file():
            index_path.unlink()
            logger.info(
                "[IGNORE_PURGE] Removed stale FAISS index %s for project %s",
                index_path,
                project_id,
            )
            return True
    except OSError as e:
        logger.warning(
            "[IGNORE_PURGE] Could not unlink FAISS index for %s: %s",
            project_id,
            e,
        )
    except Exception as e:
        logger.warning(
            "[IGNORE_PURGE] FAISS invalidate skipped for %s: %s", project_id, e
        )
    return False


def run_pre_scan_ignore_purge_for_project(
    database: Any,
    project_id: str,
    ignore_patterns: Sequence[str],
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    config_path: Optional[Path] = None,
) -> int:
    """
    Classify active files, logical-delete dependents + rows, invalidate FAISS.

    Returns number of purged file rows (0 if none).
    """
    ids = collect_file_ids_to_purge_for_ignore_policy(
        database,
        project_id,
        ignore_patterns,
        allowed_venv_py_files=allowed_venv_py_files,
        ignore_exception_files=ignore_exception_files,
    )
    if not ids:
        return 0
    lw = getattr(database, "execute_logical_write_operation", None)
    if lw is None:
        logger.warning(
            "[IGNORE_PURGE] database has no execute_logical_write_operation; skipping"
        )
        return 0
    program = build_ignore_purge_logical_write_program(
        project_id,
        ids,
        include_code_content_fts=database_has_sqlite_code_content_fts(database),
    )
    lw(program)
    try_unlink_faiss_index_for_project(project_id, config_path)
    return len(ids)
