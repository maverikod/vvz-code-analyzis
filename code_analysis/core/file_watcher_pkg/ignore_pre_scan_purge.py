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
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, cast

from code_analysis.core.database.file_purge_cascade import (
    build_file_purge_logical_write_program as build_ignore_purge_logical_write_program,
    build_file_purge_sql_batch as build_ignore_purge_sql_batch,
    database_uses_postgres,
)
from code_analysis.core.worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

from .scanner import should_ignore_path, should_prune_ignored_dir, should_skip_dir
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    database_has_sqlite_code_content_fts,
)

logger = logging.getLogger(__name__)


def _query_file_rows(
    database: Any, sql: str, params: tuple[Any, ...]
) -> List[dict[str, Any]]:
    """Return query file rows."""
    if hasattr(database, "_fetchall"):
        rows = database._fetchall(sql, params)
        return list(rows) if isinstance(rows, list) else []
    out = database.execute(
        sql,
        params,
    )
    if not isinstance(out, dict):
        return []
    data = out.get("data")
    return list(data) if isinstance(data, list) else []


def _project_root_for_id(database: Any, project_id: str) -> Optional[Path]:
    """Return project root for id."""
    from code_analysis.core.database.watch_dirs_partition import (
        current_server_instance_id,
    )

    sid = current_server_instance_id()
    rows = _query_file_rows(
        database,
        "SELECT root_path FROM projects WHERE server_instance_id = ? AND id = ? LIMIT 1",
        (sid, project_id),
    )
    if not rows:
        return None
    root = rows[0].get("root_path")
    if not root:
        return None
    try:
        return Path(str(root)).resolve()
    except OSError:
        return Path(str(root))


def collect_file_ids_to_purge_for_ignore_policy(
    database: Any,
    project_id: str,
    ignore_patterns: Sequence[str],
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    ignore_exception_patterns: Optional[Sequence[str]] = None,
    docs_indexing: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Return ``files.id`` for active rows whose path should be ignored by scanner rules.

    ``files.id`` is a UUID string on migrated schemas.

    Matches ``scan_directory`` / ``should_ignore_path`` semantics (including
    ``ignore_exception_files`` and venv allowlist).
    """
    rows = _query_file_rows(
        database,
        f"SELECT id, path, relative_path FROM files WHERE project_id = ? AND {WHERE_FILES_ACTIVE}",
        (project_id,),
    )
    project_root = _project_root_for_id(database, project_id)
    from code_analysis.core.file_identity import absolute_path_for_indexed_file

    patterns = list(ignore_patterns)
    exception_patterns = list(ignore_exception_patterns or ())
    out: List[str] = []
    for row in rows:
        fid = row.get("id")
        if fid is None:
            continue
        if not project_root:
            continue
        try:
            abs_s = absolute_path_for_indexed_file(project_root, row)
        except Exception:
            continue
        path = Path(abs_s)
        try:
            path_resolved = path.resolve()
        except OSError:
            path_resolved = path
        if should_ignore_path(
            path_resolved,
            patterns,
            allowed_venv_py_files=allowed_venv_py_files,
            ignore_exception_files=ignore_exception_files,
            ignore_exception_patterns=exception_patterns or None,
            project_root=project_root,
            docs_indexing=docs_indexing,
        ):
            out.append(str(fid))
    return out


def list_non_ignored_code_files_under_root(
    project_root: Path,
    ignore_patterns: Sequence[str],
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    ignore_exception_patterns: Optional[Sequence[str]] = None,
    docs_indexing: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, ...]:
    """
    Walk ``project_root`` with directory pruning (``should_skip_dir`` + ``should_ignore_path``).

    Returns file paths that are **not** ignored (pruned tree, same rules as
    ``scan_directory``). Used for tests and diagnostics; purge selection uses
    ``collect_file_ids_to_purge_for_ignore_policy`` on DB rows.
    """
    patterns = list(ignore_patterns)
    exception_patterns = list(ignore_exception_patterns or ())
    root = project_root.resolve()
    yielded: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dir_path = Path(dirpath)
        if should_ignore_path(
            dir_path,
            patterns,
            allowed_venv_py_files=allowed_venv_py_files,
            ignore_exception_files=ignore_exception_files,
            ignore_exception_patterns=exception_patterns or None,
            project_root=root,
            docs_indexing=docs_indexing,
        ):
            dirnames[:] = []
            continue
        pruned_dirs: List[str] = []
        for name in sorted(dirnames):
            child = dir_path / name
            if should_skip_dir(child, walk_root=root):
                continue
            if should_prune_ignored_dir(
                child,
                patterns,
                allowed_venv_py_files=allowed_venv_py_files,
                ignore_exception_files=ignore_exception_files,
                ignore_exception_patterns=exception_patterns or None,
                project_root=root,
                docs_indexing=docs_indexing,
            ):
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
                ignore_exception_patterns=exception_patterns or None,
                project_root=root,
                docs_indexing=docs_indexing,
            ):
                continue
            if fp.is_file():
                yielded.append(fp)
    return tuple(yielded)


def collect_file_ids_for_active_paths(
    database: Any, project_id: str, path_strings: Sequence[str]
) -> List[str]:
    """Resolve ``files.id`` for the given active ``path`` values under ``project_id``."""
    if not path_strings:
        return []
    out: List[str] = []
    chunk: List[str] = []
    for p in path_strings:
        chunk.append(p)
        if len(chunk) >= 400:
            out.extend(
                _collect_file_ids_for_paths_chunk(database, project_id, tuple(chunk))
            )
            chunk.clear()
    if chunk:
        out.extend(
            _collect_file_ids_for_paths_chunk(database, project_id, tuple(chunk))
        )
    return out


def _collect_file_ids_for_paths_chunk(
    database: Any, project_id: str, abs_paths: Tuple[str, ...]
) -> List[str]:
    """Return collect file ids for paths chunk."""
    if not abs_paths:
        return []
    gf = getattr(database, "get_file_by_path", None)
    if callable(gf):
        ids: List[str] = []
        for ap in abs_paths:
            row = gf(ap, project_id, include_deleted=False)
            if row and row.get("id") is not None:
                ids.append(str(row["id"]))
        return ids
    placeholders = ",".join(["?"] * len(abs_paths))
    sql = (
        f"SELECT id FROM files WHERE project_id = ? AND {WHERE_FILES_ACTIVE} "
        f"AND path IN ({placeholders})"
    )
    params = (project_id, *abs_paths)
    rows = _query_file_rows(database, sql, params)
    out: List[str] = []
    for row in rows:
        i = row.get("id")
        if i is not None:
            out.append(str(i))
    return out


def apply_ignore_purge_split_to_deltas(
    deltas: Any,
    project_id_to_root: Dict[str, Path],
    ignore_patterns: Sequence[str],
    *,
    allowed_venv_py_files: Optional[Set[Path]] = None,
    ignore_exception_files: Optional[Set[Path]] = None,
    ignore_exception_patterns: Optional[Sequence[str]] = None,
    docs_indexing: Optional[Dict[str, Any]] = None,
) -> None:
    """
    For each key in ``deltas`` (``project_id`` -> :class:`FileDelta`), move paths in
    ``deleted_files`` that are ignored-by-policy into ``ignore_purge_paths``; keep
    the rest in ``deleted_files`` for soft-delete.
    """
    from dataclasses import replace

    from .processor_delta import FileDelta

    for pid, d in list(deltas.items()):
        if not isinstance(d, FileDelta):
            continue
        root = project_id_to_root.get(pid)
        if not root:
            continue
        try:
            root_res = root.resolve()
        except OSError:
            root_res = root
        new_del: List[str] = []
        ign: List[str] = []
        exc_pat = list(ignore_exception_patterns or ())
        for path_str in d.deleted_files:
            raw = str(path_str).strip().replace("\\", "/")
            p = Path(raw)
            if p.is_absolute():
                try:
                    p_res = p.resolve()
                except OSError:
                    p_res = p
            else:
                p_res = root_res / p
                try:
                    p_res = p_res.resolve()
                except OSError:
                    p_res = root_res / p
            if should_ignore_path(
                p_res,
                list(ignore_patterns),
                allowed_venv_py_files=allowed_venv_py_files,
                ignore_exception_files=ignore_exception_files,
                ignore_exception_patterns=exc_pat or None,
                project_root=root_res,
                docs_indexing=docs_indexing,
            ):
                ign.append(path_str)
            else:
                new_del.append(path_str)
        if ign or len(new_del) != len(d.deleted_files):
            deltas[pid] = replace(d, deleted_files=new_del, ignore_purge_paths=ign)


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
    ignore_exception_patterns: Optional[Sequence[str]] = None,
    config_path: Optional[Path] = None,
    docs_indexing: Optional[Dict[str, Any]] = None,
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
        ignore_exception_patterns=ignore_exception_patterns,
        docs_indexing=docs_indexing,
    )
    if not ids:
        logger.info(
            "[IGNORE_PURGE] project_id=%s ignore_patterns_count=%d "
            "ignore_exceptions_count=%d purged_db_files_count=%d",
            project_id,
            len(ignore_patterns),
            len(ignore_exception_patterns or ()),
            0,
        )
        return 0
    from code_analysis.core.database.file_purge_cascade import (
        purge_file_ids_cascade_via_client,
    )

    purge_file_ids_cascade_via_client(
        database,
        project_id,
        ids,
        operation_name="watcher_ignore_purge",
    )
    try_unlink_faiss_index_for_project(project_id, config_path)
    logger.info(
        "[IGNORE_PURGE] project_id=%s ignore_patterns_count=%d "
        "ignore_exceptions_count=%d purged_db_files_count=%d",
        project_id,
        len(ignore_patterns),
        len(ignore_exception_patterns or ()),
        len(ids),
    )
    return len(ids)
