"""
Bulk watcher sync: disk manifest → temp diff (LEFT JOIN + purge) → INSERT/UPDATE/DELETE.

PostgreSQL only; SQLite callers use legacy per-file queue.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from code_analysis.core.database.file_purge_cascade import (
    TEMP_PURGE_TABLE,
    build_file_purge_sql_deletes_for_temp_table,
    database_uses_postgres,
)
from code_analysis.core.database.logical_write_program import (
    LogicalWriteProgramV1,
    SqlParamPair,
)
from code_analysis.core.database.logical_write_submit import (
    submit_logical_write_program_or_fallback,
)
from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    database_has_sqlite_code_content_fts,
    sql_julian_timestamp_now_expr,
)

from .watcher_disk_manifest import WatcherDiskFileRow

logger = logging.getLogger(__name__)

TEMP_DISK_RAW = "watcher_disk_raw"
TEMP_SYNC = "watcher_sync"
_INSERT_CHUNK = 400

IDX_DISK_RAW_PATH = "idx_watcher_disk_raw_path"
IDX_SYNC_ACTION = "idx_watcher_sync_action"
IDX_SYNC_PATH = "idx_watcher_sync_path"
IDX_SYNC_ACTION_EXISTING = "idx_watcher_sync_action_existing"


def _chunked_disk_raw_inserts(
    rows: Sequence[WatcherDiskFileRow],
) -> List[SqlParamPair]:
    ops: List[SqlParamPair] = []
    for i in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[i : i + _INSERT_CHUNK]
        placeholders = ",".join(["(?, ?, ?, ?, ?)"] * len(chunk))
        params: List[Any] = []
        for row in chunk:
            params.extend(
                [
                    row.relative_path,
                    row.last_modified,
                    row.lines,
                    bool(row.has_docstring),
                    row.tree_checksum,
                ]
            )
        ops.append(
            (
                f"INSERT INTO {TEMP_DISK_RAW} "
                "(relative_path, last_modified, lines, has_docstring, tree_checksum) "
                f"VALUES {placeholders}",
                tuple(params),
            )
        )
    return ops


def build_watcher_bulk_sync_program(
    project_id: str,
    watch_dir_id: Optional[str],
    disk_rows: Sequence[WatcherDiskFileRow],
    database: Any,
) -> LogicalWriteProgramV1:
    """
    Build logical-write program: load disk temp → diff temp → DML + optional purge.
    """
    if not database_uses_postgres(database):
        raise RuntimeError("build_watcher_bulk_sync_program requires PostgreSQL")

    now_expr = sql_julian_timestamp_now_expr(database)
    active_f = WHERE_FILES_ACTIVE.replace("deleted", "f.deleted")

    batch_a: List[SqlParamPair] = [
        (f"DROP TABLE IF EXISTS {TEMP_DISK_RAW}", ()),
        (
            f"CREATE TEMP TABLE {TEMP_DISK_RAW} ("
            "relative_path TEXT NOT NULL, "
            "last_modified DOUBLE PRECISION, "
            "lines INTEGER, "
            "has_docstring BOOLEAN, "
            "tree_checksum TEXT"
            ")",
            (),
        ),
    ]
    batch_a.extend(_chunked_disk_raw_inserts(disk_rows))
    batch_a.append(
        (
            f"CREATE INDEX {IDX_DISK_RAW_PATH} ON {TEMP_DISK_RAW} (relative_path)",
            (),
        )
    )

    path_match_sql = "(f.path = d.relative_path OR f.relative_path = d.relative_path)"
    change_detect_sql = (
        "f.tree_checksum IS DISTINCT FROM d.tree_checksum "
        "OR f.last_modified IS NULL "
        "OR abs(f.last_modified - d.last_modified) > 0.1"
    )

    disk_driven_sql = f"""
SELECT
  action,
  id,
  project_id,
  watch_dir_id,
  path,
  relative_path,
  lines,
  last_modified,
  has_docstring,
  tree_checksum,
  existing_file_id,
  needs_chunking
FROM (
  SELECT
    CASE
      WHEN f.id IS NULL THEN 'insert'
      WHEN {change_detect_sql} THEN 'update'
      ELSE 'skip'
    END AS action,
    COALESCE(f.id, gen_random_uuid()) AS id,
    ?::uuid AS project_id,
    ?::uuid AS watch_dir_id,
    COALESCE(d.relative_path, f.path) AS path,
    COALESCE(d.relative_path, f.relative_path, f.path) AS relative_path,
    d.lines AS lines,
    d.last_modified AS last_modified,
    d.has_docstring AS has_docstring,
    d.tree_checksum AS tree_checksum,
    f.id AS existing_file_id,
    CASE
      WHEN f.id IS NULL THEN 1
      WHEN {change_detect_sql} THEN 1
      ELSE 0
    END AS needs_chunking
  FROM {TEMP_DISK_RAW} d
  LEFT JOIN files f
    ON f.project_id = ?::uuid
   AND {active_f}
   AND {path_match_sql}
) disk_side
""".strip()

    delete_sql = f"""
SELECT
  'delete' AS action,
  f.id AS id,
  ?::uuid AS project_id,
  ?::uuid AS watch_dir_id,
  f.path AS path,
  COALESCE(f.relative_path, f.path) AS relative_path,
  NULL::integer AS lines,
  NULL::double precision AS last_modified,
  NULL::boolean AS has_docstring,
  NULL::text AS tree_checksum,
  f.id AS existing_file_id,
  0 AS needs_chunking
FROM files f
WHERE f.project_id = ?::uuid
  AND {active_f}
  AND NOT EXISTS (
    SELECT 1 FROM {TEMP_DISK_RAW} d
    WHERE d.relative_path = f.path OR d.relative_path = f.relative_path
  )
""".strip()

    sync_sql = f"""
CREATE TEMP TABLE {TEMP_SYNC} AS
{disk_driven_sql}
UNION ALL
{delete_sql}
""".strip()

    batch_b: List[SqlParamPair] = [
        (
            sync_sql,
            (
                project_id,
                watch_dir_id,
                project_id,
                project_id,
                watch_dir_id,
                project_id,
            ),
        ),
        (f"CREATE INDEX {IDX_SYNC_ACTION} ON {TEMP_SYNC} (action)", ()),
        (f"CREATE INDEX {IDX_SYNC_PATH} ON {TEMP_SYNC} (relative_path)", ()),
        (
            f"CREATE INDEX {IDX_SYNC_ACTION_EXISTING} ON {TEMP_SYNC} "
            "(action, existing_file_id) WHERE existing_file_id IS NOT NULL",
            (),
        ),
    ]

    insert_sql = f"""
INSERT INTO files (
  id, project_id, watch_dir_id, path, relative_path,
  lines, last_modified, has_docstring, tree_checksum,
  needs_chunking, deleted, created_at, updated_at
)
SELECT
  id, project_id, watch_dir_id, path, relative_path,
  lines, last_modified, has_docstring, tree_checksum,
  needs_chunking, FALSE, {now_expr}, {now_expr}
FROM {TEMP_SYNC}
WHERE action = 'insert'
ON CONFLICT (project_id, path) DO NOTHING
""".strip()

    update_sql = f"""
UPDATE files f SET
  lines = s.lines,
  last_modified = s.last_modified,
  has_docstring = s.has_docstring,
  tree_checksum = s.tree_checksum,
  deleted = FALSE,
  needs_chunking = 1,
  updated_at = {now_expr}
FROM {TEMP_SYNC} s
WHERE s.action = 'update'
  AND f.id = s.existing_file_id
  AND (f.editing_pid IS NULL)
""".strip()

    batch_c: List[SqlParamPair] = [
        (insert_sql, ()),
        (update_sql, ()),
        (f"DROP TABLE IF EXISTS {TEMP_PURGE_TABLE}", ()),
        (
            f"CREATE TEMP TABLE {TEMP_PURGE_TABLE} (id UUID NOT NULL PRIMARY KEY)",
            (),
        ),
        (
            f"INSERT INTO {TEMP_PURGE_TABLE} (id) "
            f"SELECT existing_file_id FROM {TEMP_SYNC} "
            "WHERE action = 'delete' AND existing_file_id IS NOT NULL",
            (),
        ),
    ]
    batch_c.extend(
        build_file_purge_sql_deletes_for_temp_table(
            project_id,
            TEMP_PURGE_TABLE,
            include_code_content_fts=database_has_sqlite_code_content_fts(database),
        )
    )

    return {
        "batches": [batch_a, batch_b, batch_c],
        "operation_name": "watcher_bulk_project_sync",
        "project_id": project_id,
        "lock_scope": "project_write",
    }


def submit_watcher_bulk_sync(
    database: Any,
    project_id: str,
    watch_dir_id: Optional[str],
    disk_rows: Sequence[WatcherDiskFileRow],
) -> Dict[str, int]:
    """
    Run bulk sync for one project. Returns coarse stats (manifest size based).
    """
    program = build_watcher_bulk_sync_program(
        project_id, watch_dir_id, disk_rows, database
    )
    submit_logical_write_program_or_fallback(database, program)
    n_disk = len(disk_rows)
    logger.info(
        "[BULK SYNC] project_id=%s disk_rows=%s watch_dir_id=%s",
        project_id,
        n_disk,
        watch_dir_id,
    )
    return {
        "new_files": 0,
        "changed_files": 0,
        "deleted_files": 0,
        "errors": 0,
        "disk_rows": n_disk,
    }


def bulk_sync_supported(database: Any) -> bool:
    """True when bulk PostgreSQL sync should run instead of legacy queue."""
    return database_uses_postgres(database)
