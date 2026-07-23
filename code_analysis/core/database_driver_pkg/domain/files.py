"""
File / entity CRUD, ported driver-direct (stage 2 layer collapse, Part 1).

Free-function port of the SQL-composition subset of
``code_analysis.core.database_client.client_api_files``'s ``_ClientAPIFilesMixin``
methods - i.e. everything that composes SQL over ``driver.execute``/``select``/
``insert``/``update`` (duck-typed, matching shape on both ``PostgreSQLDriver`` and
the legacy ``DatabaseClient`` - see scratchpad/stage2-parity-spike.md).

NOT ported here (already in target ``_via_driver`` shape elsewhere, per the stage-2
call map §0.4/§2b - these route through ``self.rpc_client.call(...)`` today, not SQL
composition, and their driver-package equivalents already exist):
``index_file`` -> ``core.database.files.update_standalone.update_file_data_via_driver``;
``mark_file_deleted``/``unmark_file_deleted``/``hard_delete_file``/``get_deleted_files``
-> ``core.database.files.trash_standalone.{mark_file_deleted_via_driver,
unmark_file_deleted_via_driver, hard_delete_file_via_driver, get_deleted_files_via_driver}``.

Exact-shape note: ``get_project_file_rows`` intentionally returns raw, unparsed
``last_modified`` (compared as a Unix timestamp by the file watcher against
``os.stat().st_mtime``) and must NOT be merged with ``get_project_files`` (which
returns ``File`` objects via ``db_rows_to_objects``, going through whatever
Julian-date parsing ``File.from_dict``/mappers apply) - conflating the two was a
historical bug source (mass false "changed" detection), see
``client_api_files.py``'s own docstring for ``get_project_file_rows``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.database_client.objects.file import File
from code_analysis.core.database_client.objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    sql_julian_timestamp_now_expr,
)
from code_analysis.core.database_driver_pkg.domain.projects import get_project

logger = logging.getLogger(__name__)


def create_file(driver: Any, file: File) -> File:
    """Create new file in database.

    Exact port of ``_ClientAPIFilesMixin.create_file``.
    """
    table_name = get_table_name_for_object(file)
    if table_name is None:
        raise ValueError("Unknown table for File object")

    data = object_to_db_row(file)
    driver.insert(table_name, data)

    rows = driver.select(
        table_name,
        where={
            "project_id": file.project_id,
            "path": file.path,
        },
    )
    if not rows:
        raise ValueError(
            f"Failed to create file {file.path} in project {file.project_id}"
        )

    return db_row_to_object(rows[0], File)


def get_file(driver: Any, file_id: int) -> Optional[File]:
    """Get file by ID.

    Exact port of ``_ClientAPIFilesMixin.get_file``.
    """
    rows = driver.select("files", where={"id": file_id})
    if not rows:
        return None

    return db_row_to_object(rows[0], File)


def get_file_by_id(driver: Any, file_id: int) -> Optional[Dict[str, Any]]:
    """Get file record by ID as dict (for compatibility with processor).

    Exact port of ``_ClientAPIFilesMixin.get_file_by_id``.
    """
    rows = driver.select("files", where={"id": file_id})
    return rows[0] if rows else None


def get_file_by_path(
    driver: Any, path: str, project_id: str, include_deleted: bool = False
) -> Optional[Dict[str, Any]]:
    """Resolve a filesystem path to a file row (project-relative or legacy absolute).

    Exact port of ``_ClientAPIFilesMixin.get_file_by_path``.
    """
    from code_analysis.core.path_normalization import normalize_path_simple
    from code_analysis.core.file_identity import (
        FILE_ROW_PATH_MATCH_SQL,
        file_row_path_match_values,
    )

    abs_path = normalize_path_simple(path)
    project = get_project(driver, project_id)
    if not project:
        return None
    root = project.root_path
    active = "" if include_deleted else f" AND {WHERE_FILES_ACTIVE}"
    try:
        r1, r2, r3 = file_row_path_match_values(
            project_root=root, absolute_path=abs_path
        )
    except ValueError:
        result = driver.execute(
            f"SELECT * FROM files WHERE project_id = ? AND path = ?{active}",
            (project_id, abs_path),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        return rows[0] if rows else None

    result = driver.execute(
        f"SELECT * FROM files WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
        f"{active}",
        (project_id, r1, r2, r3),
    )
    rows = result.get("data", []) if isinstance(result, dict) else []
    return rows[0] if rows else None


def add_file(
    driver: Any,
    path: str,
    lines: int,
    last_modified: float,
    has_docstring: bool,
    project_id: str,
) -> str:
    """Add or update file record. Returns file id (UUID string when DB uses UUID PK).

    Exact port of ``_ClientAPIFilesMixin.add_file``.
    """
    from code_analysis.core.file_identity import relative_path_for_project
    from code_analysis.core.path_normalization import normalize_path_simple

    abs_path = normalize_path_simple(path)
    project = get_project(driver, project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")
    raw_root = getattr(project, "root_path", None)
    if not raw_root or not Path(raw_root).is_absolute():
        raise ValueError(
            f"Project {project_id} root_path is unresolved "
            f"({raw_root!r}); cannot index files for it"
        )
    root = Path(raw_root).resolve()
    relative_path_str = relative_path_for_project(abs_path, root)
    watch_dir_id = getattr(project, "watch_dir_id", None)
    _now = sql_julian_timestamp_now_expr(driver)
    existing = get_file_by_path(driver, abs_path, project_id, include_deleted=False)
    if existing:
        file_id_raw = existing.get("id")
        if file_id_raw is None:
            driver.execute(
                "DELETE FROM files WHERE project_id = ? AND (path = ? OR relative_path = ? OR path = ?)",
                (project_id, abs_path, relative_path_str, relative_path_str),
            )
        else:
            file_id = str(file_id_raw)
            driver.execute(
                f"""
                UPDATE files
                SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?,
                    last_modified = ?, has_docstring = ?, updated_at = {_now}
                WHERE id = ?
                """,
                (
                    watch_dir_id,
                    abs_path,
                    relative_path_str,
                    lines,
                    last_modified,
                    bool(has_docstring),
                    file_id,
                ),
            )
            return file_id

    tombstone = get_file_by_path(driver, abs_path, project_id, include_deleted=True)
    if tombstone:
        file_id_raw = tombstone.get("id")
        if file_id_raw is None:
            driver.execute(
                "DELETE FROM files WHERE project_id = ? AND (path = ? OR relative_path = ? OR path = ?)",
                (project_id, abs_path, relative_path_str, relative_path_str),
            )
        else:
            file_id = str(file_id_raw)
            driver.execute(
                f"""
                UPDATE files
                SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?,
                    last_modified = ?, has_docstring = ?, deleted = 0,
                    updated_at = {_now}
                WHERE id = ?
                """,
                (
                    watch_dir_id,
                    abs_path,
                    relative_path_str,
                    lines,
                    last_modified,
                    bool(has_docstring),
                    file_id,
                ),
            )
            return file_id

    new_id = str(uuid.uuid4())
    driver.execute(
        f"""
        INSERT INTO files
        (id, project_id, watch_dir_id, path, relative_path, lines,
         last_modified, has_docstring, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, {_now})
        """,
        (
            new_id,
            project_id,
            watch_dir_id,
            abs_path,
            relative_path_str,
            lines,
            last_modified,
            bool(has_docstring),
        ),
    )
    return new_id


def add_code_content(
    driver: Any,
    file_id: int,
    entity_type: str,
    entity_name: str,
    content: str,
    docstring: Optional[str],
    entity_id: Optional[int] = None,
) -> int:
    """Add code content. Returns content id.

    Exact port of ``_ClientAPIFilesMixin.add_code_content``.
    """
    result = driver.execute(
        "INSERT INTO code_content (file_id, entity_type, entity_id, entity_name, content, docstring) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, entity_type, entity_id, entity_name, content, docstring),
    )
    row_id = result.get("lastrowid") or 0
    return row_id


def add_class(
    driver: Any,
    file_id: int,
    name: str,
    line: int,
    docstring: Optional[str],
    bases: List[str],
    end_line: Optional[int] = None,
    cst_node_id: Optional[str] = None,
) -> int:
    """Add or replace class. Returns class id.

    Exact port of ``_ClientAPIFilesMixin.add_class``.
    """
    bases_json = json.dumps(bases)
    result = driver.execute(
        "INSERT OR REPLACE INTO classes (file_id, name, line, end_line, cst_node_id, docstring, bases) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file_id, name, line, end_line, cst_node_id, docstring, bases_json),
    )
    return result.get("lastrowid", 0) or 0


def add_method(
    driver: Any,
    class_id: int,
    name: str,
    line: int,
    args: List[str],
    docstring: Optional[str],
    complexity: Optional[int] = None,
    end_line: Optional[int] = None,
    cst_node_id: Optional[str] = None,
) -> int:
    """Add or replace method. Returns method id.

    Exact port of ``_ClientAPIFilesMixin.add_method``.
    """
    args_json = json.dumps(args)
    result = driver.execute(
        "INSERT OR REPLACE INTO methods (class_id, name, line, end_line, cst_node_id, args, docstring) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (class_id, name, line, end_line, cst_node_id, args_json, docstring),
    )
    return result.get("lastrowid", 0) or 0


def add_function(
    driver: Any,
    file_id: int,
    name: str,
    line: int,
    args: List[str],
    docstring: Optional[str],
    complexity: Optional[int] = None,
    end_line: Optional[int] = None,
    cst_node_id: Optional[str] = None,
) -> int:
    """Add or replace function. Returns function id.

    Exact port of ``_ClientAPIFilesMixin.add_function``.
    """
    args_json = json.dumps(args)
    result = driver.execute(
        "INSERT OR REPLACE INTO functions (file_id, name, line, end_line, cst_node_id, args, docstring) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (file_id, name, line, end_line, cst_node_id, args_json, docstring),
    )
    return result.get("lastrowid", 0) or 0


def add_import(
    driver: Any,
    file_id: int,
    name: str,
    module: Optional[str],
    import_type: str,
    line: int,
) -> int:
    """Add import. Returns import id.

    Exact port of ``_ClientAPIFilesMixin.add_import``.
    """
    result = driver.execute(
        "INSERT INTO imports (file_id, name, module, import_type, line) "
        "VALUES (?, ?, ?, ?, ?)",
        (file_id, name, module, import_type, line),
    )
    return result.get("lastrowid", 0) or 0


def add_usage(
    driver: Any,
    file_id: int,
    line: int,
    usage_type: str,
    target_type: str,
    target_name: str,
    target_class: Optional[str] = None,
    context: Optional[str] = None,
) -> int:
    """Add usage record. Returns usage id.

    Exact port of ``_ClientAPIFilesMixin.add_usage``.
    """
    result = driver.execute(
        "INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class, context) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            file_id,
            line,
            usage_type,
            target_type,
            target_name,
            target_class,
            context,
        ),
    )
    return result.get("lastrowid", 0) or 0


def mark_file_needs_chunking(driver: Any, file_path: str, project_id: str) -> bool:
    """Mark file for re-chunking by deleting its chunks. ``file_path`` may be absolute.

    Exact port of ``_ClientAPIFilesMixin.mark_file_needs_chunking``.
    """
    from code_analysis.core.path_normalization import normalize_path_simple

    abs_path = normalize_path_simple(file_path)
    row = get_file_by_path(driver, abs_path, project_id, include_deleted=True)
    if not row:
        return False
    if row.get("deleted"):
        return False
    file_id = row.get("id")
    if file_id is None:
        return False
    driver.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
    _now = sql_julian_timestamp_now_expr(driver)
    driver.execute(
        f"UPDATE files SET needs_chunking = 1, updated_at = {_now} WHERE id = ?",
        (file_id,),
    )
    return True


def update_file(driver: Any, file: File) -> File:
    """Update existing file in database.

    Exact port of ``_ClientAPIFilesMixin.update_file``.
    """
    if file.id is None:
        raise ValueError("File id is required for update")

    existing = get_file(driver, file.id)
    if existing is None:
        raise ValueError(f"File {file.id} not found")

    data = object_to_db_row(file)
    update_data = {k: v for k, v in data.items() if k != "id"}
    driver.update("files", where={"id": file.id}, data=update_data)

    return get_file(driver, file.id) or file


def get_project_file_rows(
    driver: Any, project_id: str, include_deleted: bool = False
) -> List[Dict[str, Any]]:
    """Get file rows for a project with raw last_modified (no Julian parsing).

    Exact port of ``_ClientAPIFilesMixin.get_project_file_rows`` - see module
    docstring for why this must NOT be merged with :func:`get_project_files`.
    """
    where: Dict[str, Any] = {"project_id": project_id}
    if not include_deleted:
        where["deleted"] = 0
    rows = driver.select("files", where=where, order_by=["path"])
    return list(rows) if rows else []


def get_file_rows_by_paths(
    driver: Any,
    project_id: str,
    relative_paths: List[str],
    include_deleted: bool = False,
) -> List[Dict[str, Any]]:
    """Resolve many project-relative paths to ``files`` rows in one query.

    Page-scoped counterpart to :func:`get_project_file_rows` (bug 25c8d9dd):
    ``list_project_files`` used to load every non-deleted row for the whole
    project just to enrich one page of on-disk paths with ``file_id`` --
    O(project size) work for an O(page size) need. This mirrors
    ``IndexCoverageService._fetch_file_rows``'s query shape (``code_analysis.
    core.index_coverage``) -- same per-path candidate-value matching
    (``relative_path``, legacy relative ``path``, legacy absolute ``path``,
    via :func:`code_analysis.core.file_identity.file_row_path_match_values`)
    collapsed into exactly one ``project_id``-scoped query covering every
    requested path, instead of one query per path
    (:func:`get_file_by_path`'s per-call shape).

    Args:
        driver: Database driver/client exposing ``execute``.
        project_id: Project UUID string.
        relative_paths: Project-relative POSIX paths to resolve (typically
            one page's worth of on-disk listing results). Empty input short-
            circuits to an empty list without touching the database.
        include_deleted: When ``False`` (default), only active rows
            (mirrors :data:`~code_analysis.core.sql_portable.WHERE_FILES_ACTIVE`)
            are returned.

    Returns:
        Raw ``files`` table rows (dicts) matching any of ``relative_paths``
        for ``project_id`` -- unordered, and NOT necessarily one row per
        input path (a path with no matching row simply contributes nothing;
        callers needing a per-path map should build one from the ``id``/
        ``relative_path``/``path`` keys the same way
        :func:`code_analysis.commands.ast.list_files._build_file_id_lookup`
        does for :func:`get_project_file_rows`'s full-table shape).
    """
    if not relative_paths:
        return []

    from code_analysis.core.file_identity import file_row_path_match_values
    from code_analysis.core.path_normalization import normalize_path_simple

    project = get_project(driver, project_id)
    if project is None:
        return []
    root = project.root_path

    rel_match_values: set = set()
    path_match_values: set = set()
    for rel in relative_paths:
        abs_norm = normalize_path_simple(str((Path(root) / rel).resolve()))
        try:
            r1, r2, r3 = file_row_path_match_values(
                project_root=root, absolute_path=abs_norm
            )
        except ValueError:
            path_match_values.add(abs_norm)
            continue
        rel_match_values.add(r1)
        path_match_values.add(r2)
        path_match_values.add(r3)

    where_parts: List[str] = []
    params: List[Any] = [project_id]
    if rel_match_values:
        placeholders = ",".join(["?"] * len(rel_match_values))
        where_parts.append(f"relative_path IN ({placeholders})")
        params.extend(sorted(rel_match_values))
    if path_match_values:
        placeholders = ",".join(["?"] * len(path_match_values))
        where_parts.append(f"path IN ({placeholders})")
        params.extend(sorted(path_match_values))
    if not where_parts:
        return []

    active = "" if include_deleted else f" AND {WHERE_FILES_ACTIVE}"
    sql = (
        "SELECT * FROM files WHERE project_id = ? AND "
        f"({' OR '.join(where_parts)}){active}"
    )
    result = driver.execute(sql, tuple(params))
    rows = result.get("data", []) if isinstance(result, dict) else []
    return list(rows)


def get_project_files(
    driver: Any,
    project_id: str,
    include_deleted: bool = False,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> List[File]:
    """Get files for a project, optionally paginated.

    Exact port of ``_ClientAPIFilesMixin.get_project_files``.
    """
    where: Dict[str, Any] = {"project_id": project_id}
    if not include_deleted:
        where["deleted"] = 0

    rows = driver.select(
        "files",
        where=where,
        order_by=["path"],
        limit=limit,
        offset=offset,
    )
    return db_rows_to_objects(rows, File)


def mark_file_content_stale(driver: Any, file_path: str, project_id: str) -> bool:
    """Mark a file's content as stale after a CA-only content write (bug 56c23bd9).

    CA is the sole file-content access point for the user; ANY write to a
    file's on-disk content sets ``files.content_stale`` (and records
    ``content_stale_since``) so search results can surface the staleness
    until the next successful reindex clears it. ``file_path`` may be
    absolute. Row-resolution shape mirrors :func:`mark_file_needs_chunking`.
    """
    from code_analysis.core.path_normalization import normalize_path_simple

    abs_path = normalize_path_simple(file_path)
    row = get_file_by_path(driver, abs_path, project_id, include_deleted=True)
    if not row:
        return False
    if row.get("deleted"):
        return False
    file_id = row.get("id")
    if file_id is None:
        return False
    _now = sql_julian_timestamp_now_expr(driver)
    driver.execute(
        f"UPDATE files SET content_stale = 1, content_stale_since = {_now} WHERE id = ?",
        (file_id,),
    )
    return True
