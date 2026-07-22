"""
Build database status result dict from DB batch queries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.vector_search_backend import (
    VectorSearchBackend,
    ann_pending_sql_fragment,
    ann_ready_sql_fragment,
    driver_requires_faiss,
    uses_pgvector_ann_for_database,
)
from code_analysis.core.project_ignore_policy import (
    sql_and_absolute_path_eligible_for_default_status_aggregates as _sql_path_ok_status,
)
from code_analysis.core.sql_portable import WHERE_FILES_ACTIVE, WHERE_FILES_ACTIVE_F

# "Indexed" for status: pipeline cleared needs_chunking, or AST exists (vectorization
# backlog still uses needs_chunking=1 but content index is present).
_WHERE_FILES_INDEXED = (
    "((needs_chunking = 0 OR needs_chunking IS NULL) OR "
    "EXISTS (SELECT 1 FROM ast_trees WHERE ast_trees.file_id = files.id))"
)
_WHERE_FILES_INDEXED_F = (
    "((f.needs_chunking = 0 OR f.needs_chunking IS NULL) OR "
    "EXISTS (SELECT 1 FROM ast_trees WHERE ast_trees.file_id = f.id))"
)
_WHERE_FILES_ACTIVE_FL = "(fl.deleted IS NOT TRUE OR fl.deleted IS NULL)"

# Batch indices: 0=project_count, 1=projects_with_stats, 2=total_files, 3=deleted_files,
# 4=files_with_docstring, 5=files_needing_chunking, 6=files_with_chunks, 7=files_indexed,
# 8=files_needing_indexing, 9=total_chunks, 10=vectorized_chunks, 11=not_vectorized_chunks,
# 12=files_updated_24h, 13=chunks_updated_24h, 14=needing_indexing_sample,
# 15=needing_chunking_sample, 16=chunks_needing_vectorization


def _julian_day_threshold_sql(driver_type: str) -> str:
    """Threshold for "last 24h" filters; schema stores Julian day as DOUBLE (PostgreSQL)."""
    _ = driver_type  # kept for call-site compatibility; only "postgres" is supported
    return "EXTRACT(JULIAN FROM (CURRENT_TIMESTAMP - INTERVAL '1 day'))"


def build_status_ops(
    driver_type: str,
    *,
    vector_ann_backend: VectorSearchBackend = "faiss",
) -> List[Tuple[str, Any]]:
    """SQL batch for get_database_status; PostgreSQL uses EXTRACT(JULIAN ...).

    ``vector_ann_backend`` selects how \"vectorized\" chunks are counted: FAISS uses
    ``vector_id``; pgvector uses ``embedding_vec`` (PostgreSQL only).
    """
    j = _julian_day_threshold_sql(driver_type)
    p_files = _sql_path_ok_status("files.path")
    p_f = _sql_path_ok_status("f.path")
    p_fl = _sql_path_ok_status("fl.path")
    cc_ready = ann_ready_sql_fragment("cc", vector_ann_backend)
    cc_pending = ann_pending_sql_fragment("cc", vector_ann_backend)
    return [
        ("SELECT COUNT(*) as count FROM projects", None),
        (
            """
        SELECT
            p.id,
            p.name,
            (SELECT COUNT(*) FROM files WHERE project_id = p.id AND """
            + WHERE_FILES_ACTIVE
            + p_files
            + """) as file_count,
            (SELECT COUNT(*) FROM files WHERE project_id = p.id AND """
            + WHERE_FILES_ACTIVE
            + p_files
            + """ AND """
            + _WHERE_FILES_INDEXED
            + """) as files_indexed,
            (SELECT COUNT(DISTINCT f.id) FROM files f WHERE f.project_id = p.id AND """
            + WHERE_FILES_ACTIVE_F
            + p_f
            + """ AND EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)) as chunked_files,
            (SELECT COUNT(*) FROM code_chunks cc INNER JOIN files fl ON fl.id = cc.file_id
              WHERE cc.project_id = p.id AND """
            + _WHERE_FILES_ACTIVE_FL
            + p_fl
            + """) as chunk_count,
            (SELECT COUNT(*) FROM code_chunks cc INNER JOIN files fl ON fl.id = cc.file_id
              WHERE cc.project_id = p.id AND """
            + cc_ready
            + """ AND """
            + _WHERE_FILES_ACTIVE_FL
            + p_fl
            + """) as vectorized_chunks,
            (SELECT COUNT(DISTINCT f.id) FROM files f INNER JOIN code_chunks cc ON f.id = cc.file_id WHERE f.project_id = p.id AND """
            + WHERE_FILES_ACTIVE_F
            + p_f
            + """ AND """
            + cc_ready
            + """) as files_vectorized
        FROM projects p
        ORDER BY p.name
        """,
            None,
        ),
        ("SELECT COUNT(*) as count FROM files WHERE 1=1" + p_files, None),
        ("SELECT COUNT(*) as count FROM files WHERE deleted IS TRUE" + p_files, None),
        (
            "SELECT COUNT(*) as count FROM files WHERE has_docstring IS TRUE" + p_files,
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM files WHERE "
            + WHERE_FILES_ACTIVE
            + p_files
            + " AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = files.id)",
            None,
        ),
        (
            "SELECT COUNT(DISTINCT f.id) as count FROM files f WHERE "
            + WHERE_FILES_ACTIVE_F
            + p_f
            + " AND EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id)",
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM files WHERE "
            + WHERE_FILES_ACTIVE
            + p_files
            + " AND "
            + _WHERE_FILES_INDEXED,
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM files WHERE "
            + WHERE_FILES_ACTIVE
            + p_files
            + " AND NOT ("
            + _WHERE_FILES_INDEXED
            + ")",
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM code_chunks cc INNER JOIN files fl ON fl.id = cc.file_id WHERE "
            + _WHERE_FILES_ACTIVE_FL
            + p_fl,
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM code_chunks cc INNER JOIN files fl ON fl.id = cc.file_id WHERE "
            + _WHERE_FILES_ACTIVE_FL
            + p_fl
            + " AND "
            + cc_ready,
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM code_chunks cc INNER JOIN files fl ON fl.id = cc.file_id WHERE "
            + _WHERE_FILES_ACTIVE_FL
            + p_fl
            + " AND "
            + cc_pending
            + " AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0)",
            None,
        ),
        (
            f"SELECT COUNT(*) as count FROM files WHERE updated_at > {j}" + p_files,
            None,
        ),
        (
            "SELECT COUNT(*) as count FROM code_chunks cc INNER JOIN files fl ON fl.id = cc.file_id WHERE cc.created_at > "
            + j
            + " AND "
            + _WHERE_FILES_ACTIVE_FL
            + p_fl,
            None,
        ),
        (
            "SELECT f.id, f.path, f.has_docstring, f.last_modified FROM files f WHERE "
            + WHERE_FILES_ACTIVE_F
            + p_f
            + " AND NOT ("
            + _WHERE_FILES_INDEXED_F
            + ") ORDER BY f.updated_at ASC LIMIT 10",
            None,
        ),
        (
            "SELECT f.id, f.path, f.has_docstring, f.last_modified FROM files f WHERE "
            + WHERE_FILES_ACTIVE_F
            + p_f
            + " AND NOT EXISTS (SELECT 1 FROM code_chunks WHERE code_chunks.file_id = f.id) ORDER BY f.updated_at DESC LIMIT 10",
            None,
        ),
        (
            "SELECT cc.id, cc.file_id, cc.chunk_text, cc.created_at FROM code_chunks cc "
            "INNER JOIN files fl ON fl.id = cc.file_id WHERE "
            + cc_pending
            + " AND (cc.vectorization_skipped IS NULL OR cc.vectorization_skipped = 0) AND "
            + _WHERE_FILES_ACTIVE_FL
            + p_fl
            + " ORDER BY cc.id DESC LIMIT 10",
            None,
        ),
    ]


# Default batch (PostgreSQL is the only supported driver).
STATUS_OPS: List[tuple] = build_status_ops("postgres", vector_ann_backend="faiss")


def _postgres_pool_observability_fields(db: Any, driver_type: str) -> Dict[str, Any]:
    """Top-level pg_* pool counters for Postgres in-process; empty dict otherwise."""
    out: Dict[str, Any] = {}
    if driver_type != "postgres":
        return out
    # Stage 2 (layer collapse): db IS the PostgreSQLDriver directly once construction
    # hands it out unwrapped - check that first. Fall back to the DatabaseClient ->
    # rpc_client -> handlers -> driver chain for the pre-flip receiver shape so this
    # stays correct on both sides of the flip (pool_status() only exists on the raw
    # driver, never on DatabaseClient itself, so there is no primitive to call directly).
    if isinstance(db, PostgreSQLDriver):
        driver: Any = db
    else:
        rpc = getattr(db, "rpc_client", None)
        handlers = getattr(rpc, "handlers", None) if rpc is not None else None
        driver = getattr(handlers, "driver", None) if handlers is not None else None
    if not isinstance(driver, PostgreSQLDriver):
        return out
    pool_st = driver.pool_status()
    if not pool_st.get("enabled"):
        return out
    w = pool_st.get("write") or {}
    r = pool_st.get("read") or {}
    if "in_use" in w:
        out["pg_write_pool_in_use"] = w["in_use"]
    if "idle" in w:
        out["pg_write_pool_idle"] = w["idle"]
    if "waiters" in w:
        out["pg_write_pool_waiters"] = w["waiters"]
    if "in_use" in r:
        out["pg_read_pool_in_use"] = r["in_use"]
    if "idle" in r:
        out["pg_read_pool_idle"] = r["idle"]
    if "waiters" in r:
        out["pg_read_pool_waiters"] = r["waiters"]
    return out


def build_database_status_result(
    db: Any,
    db_path: Path,
    *,
    driver_type: str = "postgres",
    vector_ann_backend: Optional[VectorSearchBackend] = None,
) -> Dict[str, Any]:
    """
    Run status queries and build the full result dict.

    Caller must pass an open db client and the resolved db_path.
    ``driver_type`` must match ``code_analysis.database.driver.type`` (only
    "postgres" is supported) so \"last 24h\" queries use valid SQL (PostgreSQL ``EXTRACT``).

    If ``vector_ann_backend`` is omitted, it is inferred from the driver type and
    ``vector_search_backend`` on the database client (defaults to pgvector when
    permitted, else FAISS).
    """
    if vector_ann_backend is None:
        if driver_requires_faiss(driver_type):
            vector_ann_backend = "faiss"
        else:
            vector_ann_backend = (
                "pgvector" if uses_pgvector_ann_for_database(db) else "faiss"
            )

    is_pg = driver_type == "postgres"
    result: Dict[str, Any] = {
        "db_path": str(db_path),
        "database_driver": driver_type,
        "vector_ann_backend": vector_ann_backend,
        "timestamp": datetime.now().isoformat(),
        "exists": True if is_pg else (db_path.exists() if db_path else False),
        "file_size_mb": (
            0.0
            if is_pg
            else (
                db_path.stat().st_size / 1024 / 1024
                if db_path and db_path.exists()
                else 0
            )
        ),
        "projects": {},
        "files": {},
        "chunks": {},
        "recent_activity": {},
        "worker_stats": {},
    }

    batch_results = db.execute_batch(
        build_status_ops(driver_type, vector_ann_backend=vector_ann_backend)
    )

    def _row0(idx: int) -> int:
        """Return row0."""
        d = batch_results[idx].get("data", []) if idx < len(batch_results) else []
        return d[0]["count"] if d else 0

    def _data(idx: int) -> list:
        """Return data."""
        return batch_results[idx].get("data", []) if idx < len(batch_results) else []

    project_count = _row0(0)
    projects_with_stats = _data(1)
    project_list = []
    for p in projects_with_stats:
        file_count = p["file_count"] or 0
        files_indexed = p.get("files_indexed") or 0
        chunked_files = p["chunked_files"] or 0
        chunk_count = p["chunk_count"] or 0
        vectorized_chunks = p["vectorized_chunks"] or 0
        files_vectorized = p["files_vectorized"] or 0
        files_processed_by_watcher = file_count
        files_indexed_percent = (
            round((files_indexed / file_count * 100), 2) if file_count > 0 else 0
        )
        chunked_percent = (
            round((chunked_files / file_count * 100), 2) if file_count > 0 else 0
        )
        vectorized_percent = (
            round((vectorized_chunks / chunk_count * 100), 2) if chunk_count > 0 else 0
        )
        files_processed_percent = 100.0 if file_count > 0 else 0.0
        files_vectorized_percent = (
            round((files_vectorized / file_count * 100), 2) if file_count > 0 else 0
        )
        project_list.append(
            {
                "id": p["id"],
                "name": p["name"],
                "file_count": file_count,
                "files_processed_by_watcher": files_processed_by_watcher,
                "files_processed_percent": files_processed_percent,
                "files_indexed": files_indexed,
                "files_indexed_percent": files_indexed_percent,
                "files_vectorized": files_vectorized,
                "files_vectorized_percent": files_vectorized_percent,
                "chunked_files": chunked_files,
                "chunked_percent": chunked_percent,
                "chunk_count": chunk_count,
                "vectorized_chunks": vectorized_chunks,
                "vectorized_percent": vectorized_percent,
            }
        )

    result["projects"] = {"total": project_count, "sample": project_list}

    total_files = _row0(2)
    deleted_files = _row0(3)
    files_with_docstring = _row0(4)
    files_needing_chunking = _row0(5)
    files_with_chunks = _row0(6)
    files_indexed = _row0(7)
    files_needing_indexing = _row0(8)
    active_files = total_files - deleted_files
    chunked_pct = (
        round((files_with_chunks / active_files * 100), 2) if active_files > 0 else 0
    )
    indexed_pct = (
        round((files_indexed / active_files * 100), 2) if active_files > 0 else 0
    )
    result["files"] = {
        "total": total_files,
        "deleted": deleted_files,
        "active": active_files,
        "with_docstring": files_with_docstring,
        "indexed": files_indexed,
        "indexed_percent": indexed_pct,
        "needing_indexing": files_needing_indexing,
        "needing_chunking": files_needing_chunking,
        "chunked": files_with_chunks,
        "chunked_percent": chunked_pct,
    }

    total_chunks = _row0(9)
    vectorized_chunks = _row0(10)
    not_vectorized_chunks = _row0(11)
    vectorization_pct = (
        round((vectorized_chunks / total_chunks * 100), 2) if total_chunks > 0 else 0
    )
    result["chunks"] = {
        "total": total_chunks,
        "vectorized": vectorized_chunks,
        "not_vectorized": not_vectorized_chunks,
        "vectorization_percent": vectorization_pct,
    }

    result["recent_activity"] = {
        "files_updated_24h": _row0(12),
        "chunks_updated_24h": _row0(13),
    }

    get_fw = getattr(db, "get_file_watcher_stats", None)
    get_vs = getattr(db, "get_vectorization_stats", None)
    get_is = getattr(db, "get_indexing_stats", None)
    file_watcher_stats = get_fw() if callable(get_fw) else None
    vectorization_stats = get_vs() if callable(get_vs) else None
    indexing_stats = get_is() if callable(get_is) else None

    if file_watcher_stats and file_watcher_stats.get("average_processing_time_seconds"):
        avg = file_watcher_stats["average_processing_time_seconds"]
        file_watcher_stats["processing_speed_files_per_second"] = (
            round(1.0 / avg, 2) if avg and avg > 0 else None
        )
    elif file_watcher_stats:
        file_watcher_stats["processing_speed_files_per_second"] = None
    if file_watcher_stats:
        ft = file_watcher_stats.get("files_total_at_start", 0)
        fp = file_watcher_stats.get("files_processed", 0)
        file_watcher_stats["files_processed_percent"] = (
            round((fp / ft * 100), 2) if ft and ft > 0 else None
        )

    if vectorization_stats and vectorization_stats.get(
        "average_processing_time_seconds"
    ):
        avg = vectorization_stats["average_processing_time_seconds"]
        vectorization_stats["processing_speed_chunks_per_second"] = (
            round(1.0 / avg, 2) if avg and avg > 0 else None
        )
    elif vectorization_stats:
        vectorization_stats["processing_speed_chunks_per_second"] = None

    if indexing_stats and indexing_stats.get("average_processing_time_seconds"):
        avg = indexing_stats["average_processing_time_seconds"]
        indexing_stats["processing_speed_files_per_second"] = (
            round(1.0 / avg, 2) if avg and avg > 0 else None
        )
    elif indexing_stats:
        indexing_stats["processing_speed_files_per_second"] = None

    result["worker_stats"] = {
        "file_watcher": file_watcher_stats,
        "vectorization": vectorization_stats,
        "indexing": indexing_stats,
    }

    result["files"]["needing_indexing_sample"] = [
        {
            "id": f["id"],
            "path": f["path"],
            "has_docstring": bool(f["has_docstring"]),
            "last_modified": f["last_modified"],
        }
        for f in _data(14)
    ]
    result["files"]["needing_chunking_sample"] = [
        {
            "id": f["id"],
            "path": f["path"],
            "has_docstring": bool(f["has_docstring"]),
            "last_modified": f["last_modified"],
        }
        for f in _data(15)
    ]
    result["chunks"]["needing_vectorization_sample"] = [
        {
            "id": c["id"],
            "file_id": c["file_id"],
            "chunk_preview": (
                (c["chunk_text"][:100] + "...")
                if c.get("chunk_text") and len(c["chunk_text"]) > 100
                else c.get("chunk_text")
            ),
            "created_at": c["created_at"],
        }
        for c in _data(16)
    ]

    result.update(_postgres_pool_observability_fields(db, driver_type))
    return result
