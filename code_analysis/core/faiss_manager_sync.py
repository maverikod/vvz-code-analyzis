"""
FAISS index sync check: compare database vector_id set with FAISS index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Set, Tuple

# Driver-direct (stage 2): DatabaseClient class removed; ``database`` below is a
# duck-typed driver-shaped object (PostgreSQLDriver in production). Kept as an
# ``Any`` alias so the existing type annotation does not need rewriting.
DatabaseClient = Any


def check_index_sync_impl(
    index_ntotal: int,
    id_map: Any,
    database: DatabaseClient,
    project_id: str,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Check synchronization between database and FAISS index.

    Verifies that all vector_id values from database exist in FAISS index.
    Caller passes index ntotal and optional id_map (IndexIDMap2.id_map).

    Args:
        index_ntotal: Number of vectors in the index (index.ntotal).
        id_map: FAISS id_map (Int64Vector) or None for dense 0..ntotal-1.
        database: DatabaseClient — universal driver interface (RPC client).
        project_id: Project ID to check.

    Returns:
        Tuple of (is_synced, details dict).
    """
    # Get all vector_id values from database for this project
    result = database.execute(
        """
        SELECT DISTINCT vector_id
        FROM code_chunks
        WHERE project_id = ?
          AND vector_id IS NOT NULL
          AND embedding_vector IS NOT NULL
        ORDER BY vector_id
        """,
        (project_id,),
    )
    rows = result.get("data", []) if isinstance(result, dict) else []

    db_vector_ids: Set[int] = {
        row["vector_id"] for row in rows if row["vector_id"] is not None
    }
    db_vector_count = len(db_vector_ids)
    index_vector_count = int(index_ntotal)

    if id_map is not None:
        index_ids = set()
        try:
            for i in range(index_vector_count):
                index_ids.add(int(id_map.at(i)))
        except Exception:
            index_ids = set(range(index_vector_count))
    else:
        index_ids = set(range(index_vector_count))

    missing_in_index = db_vector_ids - index_ids
    extra_in_index = index_ids - db_vector_ids

    max_db_vector_id = max(db_vector_ids) if db_vector_ids else -1
    max_index_vector_id = max(index_ids) if index_ids else -1

    is_synced = (
        len(missing_in_index) == 0
        and len(extra_in_index) == 0
        and db_vector_count == index_vector_count
    )

    details = {
        "db_vector_count": db_vector_count,
        "index_vector_count": index_vector_count,
        "missing_in_index": sorted(list(missing_in_index))[:100],
        "missing_in_index_count": len(missing_in_index),
        "extra_in_index": sorted(list(extra_in_index))[:100],
        "extra_in_index_count": len(extra_in_index),
        "max_db_vector_id": max_db_vector_id,
        "max_index_vector_id": max_index_vector_id,
    }

    return is_synced, details
