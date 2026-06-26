"""
FK-safe cascade DELETE for ``files`` rows and all dependent index data.

Used when files are absent from disk or excluded by ignore policy. Submitted via
``DatabaseClient.purge_file_ids_cascade`` (logical write → driver → DB).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple, cast

from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1
from code_analysis.core.sql_portable import database_has_sqlite_code_content_fts

TEMP_PURGE_TABLE = "watcher_ignore_purge_ids"
_PURGE = f"SELECT id FROM {TEMP_PURGE_TABLE}"

_INSERT_CHUNK = 400


def database_uses_postgres(database: Any) -> bool:
    """True when the DB client is backed by PostgreSQL (strict UUID typing)."""
    return getattr(database, "_driver_type", None) == "postgres"


def _pair_issues_delete_for_purge_temp() -> Tuple[str, tuple[Any, ...]]:
    """Return pair issues delete for purge temp."""
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
    """Return pair entity cross ref delete for purge temp."""
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


def build_file_purge_sql_batch(
    project_id: str,
    file_ids: Sequence[str],
    *,
    include_code_content_fts: bool = True,
    use_uuid_temp_table: bool = False,
) -> List[Tuple[str, tuple[Any, ...]]]:
    """
    Build (sql, params) ops: CREATE TEMP, INSERT ids, then FK-safe DELETEs.

    Caller must run inside ``execute_logical_write_operation`` on a single DB connection.

    ``file_ids`` are ``files.id`` values (UUID strings after migration).

    ``use_uuid_temp_table``: When True (PostgreSQL), the temp id column is UUID so
    ``... WHERE uuid_col IN (SELECT id FROM temp)`` does not compare uuid to text.
    SQLite keeps TEXT (default False).
    """
    if not file_ids:
        return []
    pid = project_id
    ops: List[Tuple[str, tuple[Any, ...]]] = []

    ops.append((f"DROP TABLE IF EXISTS {TEMP_PURGE_TABLE}", ()))
    _id_col = (
        "UUID NOT NULL PRIMARY KEY"
        if use_uuid_temp_table
        else "TEXT NOT NULL PRIMARY KEY"
    )
    ops.append(
        (
            f"CREATE TEMP TABLE {TEMP_PURGE_TABLE} (id {_id_col})",
            (),
        )
    )

    ids_list = [str(x) for x in file_ids]
    for i in range(0, len(ids_list), _INSERT_CHUNK):
        chunk = ids_list[i : i + _INSERT_CHUNK]
        placeholders = ",".join(["(?)"] * len(chunk))
        ops.append(
            (
                f"INSERT INTO {TEMP_PURGE_TABLE} (id) VALUES {placeholders}",
                tuple(chunk),
            )
        )

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
                f"SELECT rowid FROM code_content WHERE file_id IN ({_PURGE}))",
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


def build_file_purge_sql_deletes_for_temp_table(
    project_id: str,
    temp_table: str,
    *,
    include_code_content_fts: bool = True,
) -> List[Tuple[str, tuple[Any, ...]]]:
    """
    FK-safe DELETE ops when ``temp_table`` already holds ``files.id`` values.

    Does not create or populate the temp table.
    """
    purge_sel = f"SELECT id FROM {temp_table}"
    ops: List[Tuple[str, tuple[Any, ...]]] = []
    pid = project_id

    ops.append(
        (
            f"DELETE FROM duplicate_occurrences WHERE duplicate_id IN ("
            f"SELECT DISTINCT duplicate_id FROM duplicate_occurrences "
            f"WHERE file_id IN ({purge_sel}))",
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
                f"SELECT rowid FROM code_content WHERE file_id IN ({purge_sel}))",
                (),
            )
        )

    ops.append((f"DELETE FROM code_chunks WHERE file_id IN ({purge_sel})", ()))

    issues_sql = f"""
DELETE FROM issues WHERE
  file_id IN ({purge_sel})
  OR class_id IN (SELECT id FROM classes WHERE file_id IN ({purge_sel}))
  OR method_id IN (
    SELECT id FROM methods WHERE class_id IN (
      SELECT id FROM classes WHERE file_id IN ({purge_sel})
    )
  )
  OR function_id IN (SELECT id FROM functions WHERE file_id IN ({purge_sel}))
""".strip()
    ops.append((issues_sql, ()))

    ecr_sql = f"""
DELETE FROM entity_cross_ref WHERE
  file_id IN ({purge_sel})
  OR caller_class_id IN (SELECT id FROM classes WHERE file_id IN ({purge_sel}))
  OR callee_class_id IN (SELECT id FROM classes WHERE file_id IN ({purge_sel}))
  OR caller_method_id IN (SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN ({purge_sel})))
  OR callee_method_id IN (SELECT id FROM methods WHERE class_id IN (SELECT id FROM classes WHERE file_id IN ({purge_sel})))
  OR caller_function_id IN (SELECT id FROM functions WHERE file_id IN ({purge_sel}))
  OR callee_function_id IN (SELECT id FROM functions WHERE file_id IN ({purge_sel}))
""".strip()
    ops.append((ecr_sql, ()))

    ops.append(
        (
            f"DELETE FROM methods WHERE class_id IN ("
            f"SELECT id FROM classes WHERE file_id IN ({purge_sel}))",
            (),
        )
    )
    ops.append((f"DELETE FROM classes WHERE file_id IN ({purge_sel})", ()))
    ops.append((f"DELETE FROM functions WHERE file_id IN ({purge_sel})", ()))
    ops.append((f"DELETE FROM imports WHERE file_id IN ({purge_sel})", ()))
    ops.append((f"DELETE FROM code_content WHERE file_id IN ({purge_sel})", ()))
    ops.append((f"DELETE FROM ast_trees WHERE file_id IN ({purge_sel})", ()))
    ops.append((f"DELETE FROM cst_trees WHERE file_id IN ({purge_sel})", ()))
    ops.append((f"DELETE FROM usages WHERE file_id IN ({purge_sel})", ()))
    ops.append(
        (
            f"DELETE FROM comprehensive_analysis_results WHERE file_id IN ({purge_sel})",
            (),
        )
    )
    ops.append(
        (
            "DELETE FROM file_tree_snapshot_nodes WHERE snapshot_id IN ("
            f"SELECT id FROM file_tree_snapshots WHERE file_id IN ({purge_sel}))",
            (),
        )
    )
    ops.append(
        (
            "DELETE FROM file_tree_snapshot_roots WHERE snapshot_id IN ("
            f"SELECT id FROM file_tree_snapshots WHERE file_id IN ({purge_sel}))",
            (),
        )
    )
    ops.append(
        (f"DELETE FROM file_tree_snapshots WHERE file_id IN ({purge_sel})", ()),
    )
    ops.append(
        (
            f"DELETE FROM indexing_errors WHERE project_id = ? AND file_path IN ("
            f"SELECT path FROM files WHERE id IN ({purge_sel}))",
            (pid,),
        )
    )
    ops.append(
        (
            f"DELETE FROM vector_index WHERE project_id = ? AND ("
            f"(entity_type = 'file' AND entity_id IN ({purge_sel})) OR "
            f"(entity_type = 'class' AND entity_id IN ("
            f"SELECT id FROM classes WHERE file_id IN ({purge_sel}))) OR "
            f"(entity_type = 'function' AND entity_id IN ("
            f"SELECT id FROM functions WHERE file_id IN ({purge_sel}))) OR "
            f"(entity_type = 'method' AND entity_id IN ("
            f"SELECT m.id FROM methods m JOIN classes c ON m.class_id = c.id "
            f"WHERE c.file_id IN ({purge_sel}))))",
            (pid,),
        )
    )
    ops.append((f"DELETE FROM files WHERE id IN ({purge_sel})", ()))
    return ops


def build_file_purge_logical_write_program(
    project_id: str,
    file_ids: Sequence[str],
    *,
    include_code_content_fts: bool = True,
    operation_name: str = "file_cascade_purge",
    use_uuid_temp_table: bool = False,
) -> LogicalWriteProgramV1:
    """Single-batch logical write program for file-id cascade purge."""
    batch = build_file_purge_sql_batch(
        project_id,
        file_ids,
        include_code_content_fts=include_code_content_fts,
        use_uuid_temp_table=use_uuid_temp_table,
    )
    return {
        "batches": [cast(List[Tuple[str, Sequence[Any]]], batch)],
        "operation_name": operation_name,
        "project_id": project_id,
        "lock_scope": "project_write",
    }


# Backward-compatible aliases (watcher / tests).
build_ignore_purge_sql_batch = build_file_purge_sql_batch
build_ignore_purge_logical_write_program = build_file_purge_logical_write_program


def purge_file_ids_cascade_via_client(
    database: Any,
    project_id: str,
    file_ids: Sequence[str],
    *,
    operation_name: str = "file_cascade_purge",
) -> None:
    """
    Hard-delete ``file_ids`` and all dependent rows (Command → DatabaseClient → driver).

    No-op when ``file_ids`` is empty.
    """
    if not file_ids:
        return
    from code_analysis.core.database.logical_write_submit import (
        submit_logical_write_program_or_fallback,
    )

    program = build_file_purge_logical_write_program(
        project_id,
        file_ids,
        include_code_content_fts=database_has_sqlite_code_content_fts(database),
        operation_name=operation_name,
        use_uuid_temp_table=database_uses_postgres(database),
    )
    submit_logical_write_program_or_fallback(database, program)
